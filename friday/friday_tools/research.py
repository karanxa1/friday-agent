"""Research toolset: multi-page scraping, same-site crawling, topic digests.

Builds on the SSRF-guarded fetch machinery in :mod:`friday_tools.web`:
* ``scrape_links``   -- list the links on a page (same-host first).
* ``crawl_site``     -- BFS-crawl a site (same host only) into a readable digest.
* ``research_topic`` -- search the web, scrape the top results, return a
  source-annotated digest the agent can cite from.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from core import audit
from core.config import settings
from core.registry import tool
from friday_tools.web import _log_url, _send_guarded, _strip_html, _url_error

_MAX_PAGES = 10
_HREF_RE = re.compile(r"""<a\s[^>]*href=["']([^"'#]+)(?:#[^"']*)?["']""", re.IGNORECASE)


def _extract_links(html: str, base_url: str) -> list[str]:
    """Absolute http(s) links found on a page, deduped, same-host first."""
    host = urlparse(base_url).hostname or ""
    seen: set[str] = set()
    same_host: list[str] = []
    external: list[str] = []
    for raw in _HREF_RE.findall(html):
        url = urljoin(base_url, raw.strip())
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            continue
        clean = f"{p.scheme}://{p.netloc}{p.path}"
        if clean in seen:
            continue
        seen.add(clean)
        (same_host if p.hostname == host else external).append(clean)
    return same_host + external


def _fetch_page(url: str, timeout: int = 20) -> tuple[str, str] | str:
    """Return (html, readable_text) or an 'error: …' string."""
    import httpx

    try:
        with httpx.Client(timeout=timeout) as client:
            resp, err = _send_guarded(client, "GET", url)
            if err:
                return err
            try:
                resp.read()
            finally:
                resp.close()
    except httpx.HTTPError as exc:
        return f"error: fetch failed: {exc}"
    if resp.status_code >= 400:
        return f"error: HTTP {resp.status_code} for {url}"
    ctype = resp.headers.get("content-type", "")
    raw = resp.text
    return raw, (_strip_html(raw) if "html" in ctype else raw)


@tool("research", description="List the hyperlinks on a web page (same-host links first).")
def scrape_links(url: str, contains: str = "", limit: int = 40) -> str:
    """Extract links from a page so the agent can decide what to read next.

    Args:
        url: the page to scan (http/https only; private hosts refused).
        contains: optional substring filter applied to each link.
        limit: maximum number of links to return (capped at 100).
    """
    if err := _url_error(url):
        return err
    page = _fetch_page(url)
    if isinstance(page, str):
        return page
    html, _ = page
    links = _extract_links(html, url)
    if contains:
        links = [l for l in links if contains.lower() in l.lower()]
    links = links[: max(1, min(limit, 100))]
    audit.log("research.links", url=_log_url(url), found=len(links))
    return "\n".join(links) if links else "(no links found)"


@tool("research", description="Crawl a site (same host only) and return a readable multi-page digest.")
def crawl_site(start_url: str, max_pages: int = 5, per_page_chars: int = 3000) -> str:
    """Breadth-first crawl from a start page, same host only, SSRF-guarded.

    Args:
        start_url: where to begin (http/https only; private hosts refused).
        max_pages: how many pages to read (1-10).
        per_page_chars: truncate each page's text to this many characters.
    """
    if err := _url_error(start_url):
        return err
    max_pages = max(1, min(int(max_pages), _MAX_PAGES))
    host = urlparse(start_url).hostname
    queue = [start_url]
    visited: set[str] = set()
    sections: list[str] = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        page = _fetch_page(url)
        if isinstance(page, str):
            sections.append(f"## {url}\n{page}")
            continue
        html, text = page
        sections.append(f"## {url}\n{text[:per_page_chars]}")
        for link in _extract_links(html, url):
            if urlparse(link).hostname == host and link not in visited and link not in queue:
                queue.append(link)

    audit.log("research.crawl", start=_log_url(start_url), pages=len(visited))
    return f"# Crawl of {host} ({len(visited)} pages)\n\n" + "\n\n".join(sections)


def _search(query: str, num_results: int) -> list[dict] | str:
    """Search via the CallMissed API directly (no MCP hop)."""
    import httpx

    if not settings.callmissed_api_key:
        return "error: CALLMISSED_API_KEY not set — cannot search. Scrape known URLs instead."
    try:
        resp = httpx.post(
            f"{settings.callmissed_base_url.rstrip('/')}/v1/search",
            headers={"Authorization": f"Bearer {settings.callmissed_api_key}"},
            json={"query": query, "mode": "auto", "num_results": num_results},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return f"error: search failed: {exc}"
    if resp.status_code != 200:
        return f"error: search returned HTTP {resp.status_code}"
    try:
        return list(resp.json().get("results") or [])
    except (json.JSONDecodeError, ValueError):
        return "error: search returned malformed JSON"


@tool("research", description="Research a topic: search the web, scrape top results, return a cited digest.")
def research_topic(query: str, max_pages: int = 4, per_page_chars: int = 2500) -> str:
    """Search + scrape in one step for deep research.

    Args:
        query: what to research.
        max_pages: how many top results to scrape (1-8).
        per_page_chars: truncate each page's text to this many characters.
    """
    max_pages = max(1, min(int(max_pages), 8))
    results = _search(query, num_results=max_pages * 2)
    if isinstance(results, str):
        return results
    if not results:
        return f"(no search results for {query!r})"

    sections: list[str] = []
    scraped = 0
    for r in results:
        if scraped >= max_pages:
            break
        url = str(r.get("url") or "")
        title = str(r.get("title") or url)
        snippet = str(r.get("snippet") or "")
        if not url or _url_error(url):
            continue
        page = _fetch_page(url)
        body = snippet if isinstance(page, str) else page[1][:per_page_chars]
        sections.append(f"## {title}\nSource: {url}\n{body}")
        scraped += 1

    audit.log("research.topic", query=query[:120], pages=scraped)
    if not sections:
        return f"(search found results for {query!r} but none could be scraped)"
    return f"# Research: {query} ({scraped} sources)\n\n" + "\n\n".join(sections)
