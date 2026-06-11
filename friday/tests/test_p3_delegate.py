"""P3 verification: spawn_subagent (tier routing, depth cap, real child run)."""

from __future__ import annotations

import asyncio

import pytest

from control_plane import builder


def test_child_toolsets_grants_full_access():
    from delegate.spawn import _child_toolsets

    builder.import_tool_modules()
    # Sub-agents get the full toolset (gated actions still go through the
    # approval queue) and can always delegate further (bounded by depth+breadth).
    ts = _child_toolsets()
    assert "delegate" in ts
    assert "self_dev" in ts
    assert "files" in ts
    assert "browser" in ts
    # Scheduler-owned toolsets are excluded from one-shot children.
    assert "automations" not in ts


def test_fanout_cap(monkeypatch):
    import delegate.spawn as sp
    from core.config import settings

    # Exhaust the per-turn breadth budget and confirm refusal.
    token = sp._fanout.set(settings.max_fanout)
    try:
        out = asyncio.run(sp.spawn_subagent("do something", role="leaf"))
    finally:
        sp._fanout.reset(token)
    assert "fan-out limit" in out


def test_depth_cap(monkeypatch):
    import delegate.spawn as sp
    from core.config import settings

    # Force depth to the cap and confirm refusal.
    token = sp._depth.set(settings.max_spawn_depth)
    try:
        out = asyncio.run(sp.spawn_subagent("do something", role="leaf"))
    finally:
        sp._depth.reset(token)
    assert "max spawn depth" in out


def test_spawn_runs_real_child():
    import delegate.spawn as sp

    builder.import_tool_modules()
    out = asyncio.run(sp.spawn_subagent("Reply with the single word DELEGATED.", force_tier="easy"))
    assert out and len(out) > 0


def test_registered_in_delegate_toolset():
    from core.registry import registry

    builder.import_tool_modules()
    names = {t.name for t in registry.list() if t.toolset == "delegate"}
    assert "spawn_subagent" in names
