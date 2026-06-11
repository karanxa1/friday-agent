"""P16: research toolset (link extraction, crawl guards, search digest)."""

from __future__ import annotations

from friday_tools.research import _extract_links, crawl_site, research_topic, scrape_links

_HTML = """
<html><body>
  <a href="/docs">Docs</a>
  <a href="https://example.com/about#team">About</a>
  <a href="https://other.org/page?q=1">External</a>
  <a href="mailto:hi@example.com">Mail</a>
  <a href="/docs">Dup</a>
</body></html>
"""


def test_extract_links_absolute_dedup_same_host_first():
    links = _extract_links(_HTML, "https://example.com/start")
    assert links[0] == "https://example.com/docs"
    assert "https://example.com/about" in links  # fragment stripped
    assert links[-1] == "https://other.org/page"  # external last, query dropped
    assert len(links) == 3  # deduped, mailto skipped


def test_scrape_links_refuses_private_hosts():
    out = scrape_links("http://127.0.0.1:8080/")
    assert out.startswith("error:")


def test_crawl_site_refuses_private_hosts():
    out = crawl_site("http://localhost/admin")
    assert out.startswith("error:")


def test_research_topic_without_key_explains():
    # Patch the settings object the module actually reads — earlier suite tests
    # may hot-reload modules, leaving multiple Settings instances alive.
    import friday_tools.research as research_mod

    settings = research_mod.settings
    old = settings.callmissed_api_key
    object.__setattr__(settings, "callmissed_api_key", "")
    try:
        out = research_mod.research_topic("anything")
        assert out.startswith("error:") and "CALLMISSED_API_KEY" in out
    finally:
        object.__setattr__(settings, "callmissed_api_key", old)
