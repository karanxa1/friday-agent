"""Web tools (ported from the reference ``tools/web_tools.py`` + ``url_safety``).

``fetch_url`` extracts readable text from a page; ``download_file`` saves a
remote file into the workspace. Both refuse private/loopback addresses so the
agent cannot probe the local network (SSRF guard, the reference ``url_safety.py``).
"""

from __future__ import annotations

import html as _html
import ipaddress
import re
import socket
from urllib.parse import urlparse

from core import audit
from core.registry import tool

_MAX_FETCH = 12_000
_MAX_DOWNLOAD = 10 * 1024 * 1024  # 10 MB
_MAX_REDIRECTS = 5
_UA = {"User-Agent": "friday-agent/1.0"}


def _log_url(url: str) -> str:
    """URL with query string dropped — query params can carry secrets/tokens."""
    try:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}{p.path}"
        return (base + "?…") if p.query else base
    except ValueError:
        return url[:120]


def _url_error(url: str) -> str | None:
    """Validate scheme + resolve host; refuse private/loopback ranges."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return f"error: invalid URL {url!r}"
    if parsed.scheme not in ("http", "https"):
        return f"error: only http/https URLs are allowed (got {parsed.scheme!r})"
    host = parsed.hostname or ""
    if not host:
        return "error: URL has no host"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return f"error: cannot resolve host {host!r}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"error: {host!r} resolves to a private/loopback address; refusing"
    return None


def _send_guarded(client, method: str, url: str):
    """Follow redirects manually, re-validating EVERY hop against the private
    address guard (a public host must not redirect us to localhost). Residual
    risk: DNS rebinding between validation and connect is not pinned.

    Returns (response, None) with an open streaming response, or (None, error).
    """
    import httpx

    for _ in range(_MAX_REDIRECTS + 1):
        if err := _url_error(url):
            return None, err
        req = client.build_request(method, url, headers=_UA)
        resp = client.send(req, stream=True, follow_redirects=False)
        if resp.is_redirect:
            location = resp.headers.get("location", "")
            resp.close()
            if not location:
                return None, "error: redirect without a Location header"
            url = str(httpx.URL(url).join(location))
            continue
        return resp, None
    return None, f"error: more than {_MAX_REDIRECTS} redirects"


def _strip_html(raw: str) -> str:
    """Cheap readable-text extraction: drop script/style, tags, collapse space."""
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = _html.unescape(raw)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", raw)).strip()


@tool("web", description="Fetch a web page and return its readable text content.")
def fetch_url(url: str, max_chars: int = _MAX_FETCH) -> str:
    """Fetch an http(s) URL and extract readable text.

    Args:
        url: the page to fetch (http/https only; private hosts refused).
        max_chars: truncate the extracted text to this many characters.
    """
    import httpx

    try:
        with httpx.Client(timeout=20) as client:
            resp, err = _send_guarded(client, "GET", url)
            if err:
                return err
            try:
                resp.read()
            finally:
                resp.close()
    except httpx.HTTPError as exc:
        return f"error: fetch failed: {exc}"
    audit.log("web.fetch", url=_log_url(url), status=resp.status_code, bytes=len(resp.content))
    if resp.status_code >= 400:
        return f"error: HTTP {resp.status_code} for {url}"
    ctype = resp.headers.get("content-type", "")
    text = _strip_html(resp.text) if "html" in ctype else resp.text
    if len(text) > max_chars:
        return text[:max_chars] + f"\n… (truncated, {len(text)} chars total)"
    return text or "(empty page)"


@tool("web", description="Download a remote file into the agent workspace (downloads/).")
def download_file(url: str, filename: str) -> str:
    """Download a file to ``workspace/downloads/<filename>``.

    Args:
        url: the file URL (http/https only; private hosts refused).
        filename: target name inside workspace/downloads (no path separators).
    """
    import httpx

    from friday_tools.files import _safe_path

    if "/" in filename or "\\" in filename or filename.startswith("."):
        return "error: filename must be a plain name without separators"
    target = _safe_path(f"downloads/{filename}")
    if target is None:
        return "error: invalid download path"
    try:
        with httpx.Client(timeout=60) as client:
            resp, err = _send_guarded(client, "GET", url)
            if err:
                return err
            try:
                if resp.status_code >= 400:
                    return f"error: HTTP {resp.status_code} for {url}"
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with target.open("wb") as fh:
                    for chunk in resp.iter_bytes():
                        written += len(chunk)
                        if written > _MAX_DOWNLOAD:
                            fh.close()
                            target.unlink(missing_ok=True)
                            return f"error: file exceeds {_MAX_DOWNLOAD // (1024 * 1024)} MB limit"
                        fh.write(chunk)
            finally:
                resp.close()
    except httpx.HTTPError as exc:
        return f"error: download failed: {exc}"
    audit.log("web.download", url=_log_url(url), file=filename, bytes=written)
    return f"downloaded {written} bytes to downloads/{filename}"
