"""P2 verification: skills system (create/list/view/patch/delete + provenance)."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def temp_home(monkeypatch):
    """Isolate FRIDAY_HOME to a temp dir (Friday test pattern)."""
    d = tempfile.mkdtemp(prefix="friday-test-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    # Rebuild settings to pick up the env var.
    import importlib

    import core.config as cfg

    importlib.reload(cfg)
    # Re-point modules that captured settings at import.
    import skills.usage as usage
    import skills.manager as manager

    importlib.reload(usage)
    importlib.reload(manager)
    yield d


SAMPLE = """---
name: greet
description: Say hello in a friendly way.
---

# Greet Skill

When asked to greet, respond warmly.
"""


def test_create_list_view():
    import skills.manager as m

    assert "created" in m.skill_create("greet", SAMPLE)
    listing = m.skill_list()
    assert "greet" in listing and "friendly" in listing
    body = m.skill_view("greet")
    assert "Greet Skill" in body


def test_create_rejects_bad_frontmatter():
    import skills.manager as m

    out = m.skill_create("bad", "no frontmatter here")
    assert out.startswith("error")


def test_patch_and_delete():
    import skills.manager as m

    m.skill_create("greet", SAMPLE)
    assert "patched" in m.skill_patch("greet", "respond warmly", "respond very warmly")
    assert "very warmly" in m.skill_view("greet")
    assert "deleted" in m.skill_delete("greet")
    assert m.skill_view("greet").startswith("error")


def test_provenance_marks_agent_created():
    import skills.manager as m
    import skills.usage as usage
    from skills.provenance import set_current_write_origin, reset_current_write_origin, BACKGROUND_REVIEW

    tok = set_current_write_origin(BACKGROUND_REVIEW)
    try:
        m.skill_create("autoskill", SAMPLE.replace("greet", "autoskill"))
    finally:
        reset_current_write_origin(tok)
    info = usage.get("autoskill")
    assert info is not None and info["created_by"] == "agent"
