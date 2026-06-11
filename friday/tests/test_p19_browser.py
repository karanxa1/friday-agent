"""P19: browser toolset (real headless Chromium via Playwright).

A live navigate → snapshot → screenshot flow against a stable public page,
plus registration + SSRF-guard checks. Skips gracefully if the Playwright
browser binary isn't installed in this environment.
"""

from __future__ import annotations

import asyncio

import pytest

from control_plane import builder


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        import os

        return bool(path) and os.path.exists(path)
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _chromium_available(), reason="playwright chromium not installed"
)


def test_browser_tools_registered():
    builder.import_tool_modules()
    from core.registry import registry

    names = {e.name for e in registry.list() if e.toolset == "browser"}
    assert {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "browser_extract_text",
        "browser_back",
        "browser_close",
    } <= names


def test_browser_navigate_refuses_private_host():
    from friday_tools.browser import browser_navigate

    out = asyncio.run(browser_navigate("http://127.0.0.1:8080/"))
    assert "private/loopback" in out or "refusing" in out


def test_browser_navigate_requires_url():
    from friday_tools.browser import browser_navigate

    assert "url is required" in asyncio.run(browser_navigate(""))


def test_browser_flow_navigate_snapshot_screenshot():
    """End-to-end: open a real page, list elements, screenshot it, then close."""
    from friday_tools import browser as br

    async def run() -> tuple[str, str, str]:
        nav = await br.browser_navigate("https://example.com")
        snap = await br.browser_snapshot()
        shot = await br.browser_screenshot()
        await br.browser_close()
        return nav, snap, shot

    nav, snap, shot = asyncio.run(run())
    assert "Example Domain" in nav
    # example.com has a single "More information..." link.
    assert "interactive elements" in snap or "no visible" in snap
    assert "screenshot saved" in shot
    assert ".png" in shot
