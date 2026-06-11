"""Browser toolset: a real headless Chromium the agent can drive (Playwright).

Unlike ``friday_tools.web`` (HTTP-level fetch — no JS, no interaction), this
gives the agent a live browser it can navigate, read, click, type into and
screenshot — so it can use JS-heavy sites, fill forms and *see* rendered pages.
Inspired by the reference ``tools/browser_tool.py``.

Design:
  * One lazily-launched async-Playwright session per process, reused across
    calls, so ``navigate → snapshot → click → type → screenshot`` is a flow.
  * ``browser_snapshot`` numbers the interactive elements; ``browser_click`` /
    ``browser_type`` take those numbers (``ref``) — stable, model-friendly
    addressing that doesn't depend on brittle CSS selectors.
  * Screenshots are saved under ``workspace/images/`` and surfaced to the UI by
    the streaming bridge's image-path detector (rendered inline, kept out of
    model context).
  * Navigation reuses the SSRF guard from ``friday_tools.web`` — the browser
    will not open private/loopback addresses.

Safety: arbitrary browsing is powerful. The session runs headless with a fixed
desktop viewport; downloads are not auto-accepted; JS dialogs are auto-dismissed.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from core import audit
from core.config import settings
from core.registry import tool

# ── session singleton ──────────────────────────────────────────────────────
# Held at module scope so a multi-step task reuses one browser/page. Guarded by
# a lock so concurrent tool calls (e.g. parallel sub-agents) don't race the
# lazy launch.
_pw: Any = None
_browser: Any = None
_context: Any = None
_page: Any = None
_lock = asyncio.Lock()
# The visible interactive elements from the most recent browser_snapshot, in
# the SAME order they were numbered. browser_click/browser_type index into this
# directly so a ref always resolves to the element the model actually saw —
# re-querying the DOM (which may have mutated, or enumerate differently) would
# silently act on the wrong element.
_snapshot: list[Any] = []
# Keep references to in-flight dialog-dismiss tasks so they aren't GC'd.
_pending: set[asyncio.Task] = set()

_NAV_TIMEOUT = 30_000  # ms
_ACT_TIMEOUT = 10_000  # ms
_MAX_TEXT = 12_000
_VIEWPORT = {"width": 1280, "height": 800}
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 friday-agent/1.0"
)

# Interactive elements we expose in a snapshot, in priority order.
_INTERACTIVE = "a, button, input, textarea, select, [role=button], [role=link], [onclick]"


async def _ensure_page():
    """Launch (once) and return the live page, creating the browser lazily.

    Uses a *persistent* context (a real on-disk Chromium profile) so logins the
    user performs in the visible window survive across runs. Headed by default
    (so a human can sign in); set FRIDAY_BROWSER_HEADLESS=1 for servers/CI.

    Self-heals if the existing session is bound to a different/closed event loop
    (can happen across separate ``asyncio.run`` entries or after a runner is
    torn down): tears the stale session down and relaunches on this loop.
    """
    global _pw, _context, _page
    if _page is not None and not _page.is_closed():
        return _page

    async def _launch():
        global _pw, _context, _page
        from playwright.async_api import async_playwright

        from core.config import settings

        if _pw is None:
            _pw = await async_playwright().start()
        profile = settings.browser_profile_dir
        profile.mkdir(parents=True, exist_ok=True)
        # launch_persistent_context returns a context that owns the browser and
        # writes cookies/localStorage to the profile dir → persistent login.
        _context = await _pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=settings.browser_headless,
            viewport=_VIEWPORT,
            user_agent=_UA,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        _page = _context.pages[0] if _context.pages else await _context.new_page()

    try:
        await _launch()
    except Exception:  # noqa: BLE001 — likely a stale loop or locked profile
        await _teardown_quiet()
        await _launch()
    _snapshot.clear()

    def _dialog(d):
        t = asyncio.create_task(d.dismiss())
        _pending.add(t)
        t.add_done_callback(_pending.discard)

    # Auto-dismiss JS dialogs so a stray alert() can't wedge the session.
    _page.on("dialog", _dialog)
    return _page


async def _teardown_quiet() -> None:
    """Best-effort teardown of the session (ignores errors from a dead loop)."""
    global _pw, _browser, _context, _page
    for obj, meth in ((_context, "close"), (_browser, "close"), (_pw, "stop")):
        try:
            if obj is not None:
                await getattr(obj, meth)()
        except Exception:  # noqa: BLE001
            pass
    _pw = _browser = _context = _page = None
    _snapshot.clear()


def _images_dir():
    d = settings.home / "workspace" / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_guard(url: str) -> str | None:
    """Reuse the web toolset's SSRF guard (private/loopback hosts refused)."""
    from friday_tools.web import _url_error

    return _url_error(url)


def _resolve_local_artifact(url: str) -> Path | None:
    """Map a reference to a file the agent generated to a local path.

    The box is IP-locked, so it can't reach its own public ``/api/files`` URL
    from inside — and ``file://`` was being mangled into ``https://file://``.
    This resolves ``file://…``, ``/api/files/<name>``, the absolute public URL
    form, ``artifacts/<name>``, a bare artifact filename, or an absolute path —
    but ONLY to files inside the agent home, so the agent can open its own
    HTML/SVG/PDF straight from disk (no network). Returns None for anything
    external or outside the home (those go through the normal http path)."""
    s = (url or "").strip()
    if not s:
        return None
    home = settings.home.resolve()
    ad = settings.artifacts_dir.resolve()
    cand: Path | None = None
    if s.startswith("file://"):
        from urllib.parse import unquote, urlparse

        cand = Path(unquote(urlparse(s).path))
    else:
        prefixes = [
            (settings.public_url.rstrip("/") + "/api/files/") if settings.public_url else "",
            "/api/files/",
            "artifacts/",
        ]
        for pref in prefixes:
            if pref and s.startswith(pref):
                cand = ad / os.path.basename(s[len(pref):])
                break
        if cand is None and "://" not in s:
            p = Path(s)
            if p.is_absolute():
                cand = p
            elif (ad / os.path.basename(s)).is_file():
                cand = ad / os.path.basename(s)
    if cand is None:
        return None
    try:
        rp = cand.resolve()
        rp.relative_to(home)  # only files inside the agent home
    except (ValueError, OSError):
        return None
    return rp if rp.is_file() else None


# ── tools ───────────────────────────────────────────────────────────────────


@tool("browser", description="Open a URL (or a local artifact you generated) in a real headless browser and return page text.")
async def browser_navigate(url: str = "", max_chars: int = _MAX_TEXT) -> str:
    """Navigate the browser to ``url`` and return the page title + visible text.

    Use this for JS-heavy/interactive sites where ``fetch_url`` (HTTP only)
    falls short. The page stays open for follow-up clicks/typing/screenshots.

    To preview an HTML/SVG file YOU generated, pass its artifact name, its
    ``/api/files/<name>`` link, or a ``file://`` path — it opens straight from
    disk (the host is IP-locked, so its own public URL is unreachable from
    inside).

    Args:
        url: http/https URL, or a local artifact (name / link / file://).
        max_chars: truncate returned page text to this many characters.
    """
    url = (url or "").strip()
    if not url:
        return "error: url is required"
    # Local artifact? Open it from disk via file:// (no network round-trip).
    local = _resolve_local_artifact(url)
    if local is not None:
        url = local.as_uri()
    else:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if err := _url_guard(url):
            return err
    async with _lock:
        try:
            page = await _ensure_page()
            resp = await page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
            status = resp.status if resp else 0
            title = await page.title()
            try:
                text = await page.inner_text("body", timeout=_ACT_TIMEOUT)
            except Exception:  # noqa: BLE001
                text = ""
            page_url = page.url
        except Exception as exc:  # noqa: BLE001
            return f"error: navigation failed: {str(exc)[:200]}"
        _snapshot.clear()  # new page — old refs are stale
    audit.log("browser.navigate", url=url[:120], status=status, title=title[:80])
    body = text.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n… (truncated, {len(text)} chars total)"
    return f"[{status}] {title}\nURL: {page_url}\n\n{body or '(no visible text)'}"


@tool("browser", description="List the page's interactive elements (links/buttons/inputs) numbered for clicking.")
async def browser_snapshot(limit: int = 50) -> str:
    """Return a numbered list of interactive elements on the current page.

    Each line is ``[n] <tag> "label"`` — pass ``n`` as ``ref`` to
    ``browser_click`` / ``browser_type``. Call this after navigating to see
    what you can act on. The numbering matches what click/type resolve against
    (visible elements only), so a ref always hits the element you saw.

    Args:
        limit: max elements to list.
    """
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        try:
            handles = await _page.query_selector_all(_INTERACTIVE)
            rows: list[str] = []
            _snapshot.clear()
            for h in handles:
                if len(_snapshot) >= limit:
                    break
                try:
                    if not await h.is_visible():
                        continue
                    tag = (await h.evaluate("e => e.tagName")).lower()
                    label = (
                        (await h.inner_text()).strip()
                        or (await h.get_attribute("aria-label") or "")
                        or (await h.get_attribute("placeholder") or "")
                        or (await h.get_attribute("value") or "")
                        or (await h.get_attribute("name") or "")
                        or (await h.get_attribute("href") or "")
                    )
                    label = " ".join(label.split())[:80]
                    # Number is the index into the cached visible list — the
                    # exact list click/type index into.
                    rows.append(f"[{len(_snapshot)}] <{tag}> {label!r}")
                    _snapshot.append(h)
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            return f"error: snapshot failed: {str(exc)[:200]}"
    audit.log("browser.snapshot", count=len(rows))
    if not rows:
        return "(no visible interactive elements found)"
    return f"{len(rows)} interactive elements:\n" + "\n".join(rows)


def _ref_handle(ref: int):
    """Resolve a snapshot ref to its cached element handle (or None)."""
    if ref < 0 or ref >= len(_snapshot):
        return None
    return _snapshot[ref]


@tool("browser", description="Click an interactive element by its snapshot number (ref).")
async def browser_click(ref: int = -1) -> str:
    """Click the element numbered ``ref`` from the latest ``browser_snapshot``.

    Args:
        ref: the element number to click.
    """
    if ref < 0:
        return "error: ref is required (the [n] from browser_snapshot)"
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        if not _snapshot:
            return "error: call browser_snapshot first to number the elements"
        try:
            h = _ref_handle(ref)
            if h is None:
                return f"error: no element at ref {ref} (snapshot has {len(_snapshot)})"
            label = " ".join((await h.inner_text()).split())[:60]
            await h.click(timeout=_ACT_TIMEOUT)
            await _page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT)
            url = _page.url
            title = await _page.title()
        except Exception as exc:  # noqa: BLE001
            return f"error: click failed: {str(exc)[:200]}"
        # The DOM likely changed — the old refs are stale; require a re-snapshot.
        _snapshot.clear()
    audit.log("browser.click", ref=ref)
    return f"clicked [{ref}] {label!r} — now at {url}\nTitle: {title}\n(elements changed — call browser_snapshot again before clicking)"


@tool("browser", description="Type text into an input element by its snapshot number (ref), optionally submit.")
async def browser_type(ref: int = -1, text: str = "", submit: bool = False) -> str:
    """Type ``text`` into the element numbered ``ref``.

    Args:
        ref: the input/textarea number from browser_snapshot.
        text: the text to type.
        submit: press Enter after typing (e.g. to submit a search box).
    """
    if ref < 0:
        return "error: ref is required (the [n] from browser_snapshot)"
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        if not _snapshot:
            return "error: call browser_snapshot first to number the elements"
        try:
            h = _ref_handle(ref)
            if h is None:
                return f"error: no element at ref {ref} (snapshot has {len(_snapshot)})"
            await h.fill(text, timeout=_ACT_TIMEOUT)
            url = _page.url
            if submit:
                await h.press("Enter")
                await _page.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT)
                url = _page.url
                _snapshot.clear()  # submit navigated/changed the page
        except Exception as exc:  # noqa: BLE001
            return f"error: type failed: {str(exc)[:200]}"
    audit.log("browser.type", ref=ref, submit=submit, chars=len(text))
    suffix = f" and submitted — now at {url}" if submit else ""
    return f"typed into [{ref}]{suffix}"


@tool("browser", description="Screenshot the current page (saved to workspace; shown inline).")
async def browser_screenshot(full_page: bool = False) -> str:
    """Capture a PNG of the current page.

    Args:
        full_page: capture the entire scrollable page (not just the viewport).
    """
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        path = _images_dir() / f"shot_{int(time.time())}.png"
        try:
            await _page.screenshot(path=str(path), full_page=full_page, timeout=_NAV_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return f"error: screenshot failed: {str(exc)[:200]}"
        title = await _page.title()
    audit.log("browser.screenshot", file=path.name, full_page=full_page)
    return f"screenshot saved: {path}\npage: {title} ({_page.url})"


@tool("browser", description="Get the current page's readable text again (after JS updates).")
async def browser_extract_text(max_chars: int = _MAX_TEXT) -> str:
    """Return the current page's visible text (re-read after interactions)."""
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        try:
            text = (await _page.inner_text("body", timeout=_ACT_TIMEOUT)).strip()
            title = await _page.title()
        except Exception as exc:  # noqa: BLE001
            return f"error: extract failed: {str(exc)[:200]}"
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n… (truncated, {len(text)} chars total)"
    return f"{title} ({_page.url})\n\n{text or '(no visible text)'}"


@tool("browser", description="Go back to the previous page in browser history.")
async def browser_back() -> str:
    """Navigate back one entry in the browser history."""
    async with _lock:
        if _page is None or _page.is_closed():
            return "error: no page open — call browser_navigate first"
        try:
            await _page.go_back(timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
            url = _page.url
            title = await _page.title()
        except Exception as exc:  # noqa: BLE001
            return f"error: back failed: {str(exc)[:200]}"
        _snapshot.clear()
    audit.log("browser.back", url=url[:120])
    return f"went back — now at {url}\nTitle: {title}"


@tool("browser", description="Close the browser session and free its resources.")
async def browser_close() -> str:
    """Close the browser. A later browser_navigate launches a fresh session."""
    global _pw, _browser, _context, _page
    async with _lock:
        try:
            if _context is not None:
                await _context.close()
            if _browser is not None and _browser.is_connected():
                await _browser.close()
            if _pw is not None:
                await _pw.stop()
        except Exception as exc:  # noqa: BLE001
            return f"error: close failed: {str(exc)[:200]}"
        finally:
            _pw = _browser = _context = _page = None
            _snapshot.clear()
    audit.log("browser.close")
    return "browser closed"
