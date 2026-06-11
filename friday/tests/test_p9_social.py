"""P9 verification: social-media pack (gated publisher/ads + a live loop stage)."""

from __future__ import annotations

import asyncio
import importlib
import json
import tempfile

import pytest

from control_plane import builder


@pytest.fixture(autouse=True)
def temp_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="friday-p9-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    monkeypatch.setenv("FRIDAY_AUTONOMY", "L1")
    import core.config as cfg

    importlib.reload(cfg)
    import control_plane.approvals as ap

    importlib.reload(ap)
    import domains.social_media.tools as t

    importlib.reload(t)
    yield d


def test_queue_post_is_gated():
    import domains.social_media.tools as t
    import control_plane.approvals as ap

    out = t.queue_post("x", "We shipped a faster debugger.")
    assert "queued post" in out
    pend = ap.pending()
    assert len(pend) == 1 and pend[0]["type"] == "publish"
    aid = pend[0]["id"]

    # cannot publish before approval
    assert t.confirm_publish(aid).startswith("error")
    ap.decide(aid, approve=True)
    assert "published" in t.confirm_publish(aid)
    posts = json.loads(t.list_queue())["posts"]
    assert len(posts) == 1 and posts[0]["status"] == "published"


def test_ad_budget_change_is_gated():
    import domains.social_media.tools as t
    import control_plane.approvals as ap

    out = t.adjust_budget("c_launch_x", 180.0, reason="scaling winner")
    assert "staged budget change" in out
    aid = ap.pending()[0]["id"]
    assert t.confirm_campaign(aid).startswith("error")  # not approved
    ap.decide(aid, approve=True)
    assert "budget" in t.confirm_campaign(aid)
    camps = json.loads(t.list_campaigns())["campaigns"]
    assert any(c["id"] == "c_launch_x" and c["daily_budget"] == 180.0 for c in camps)


def test_brand_profile_loads():
    from domains.social_media import agents as A

    brand = A.load_brand()
    assert brand["brand"] == "Acme Devtools"
    assert "x" in brand["platforms"]


def test_analyst_stage_runs_live():
    """Analyst reads mock metrics via MCP and produces recommendations."""
    from domains.social_media import agents as A
    from core.conversation import run_once

    builder.import_tool_modules()
    analyst = A.build_analyst()
    out = asyncio.run(run_once(analyst, "Analyze performance and recommend actions."))
    assert out and len(out) > 20
