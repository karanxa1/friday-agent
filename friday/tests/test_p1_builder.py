"""P1 verification: builder constructs the root agent, it runs, hot-reload works."""

from __future__ import annotations

import asyncio

from control_plane import builder
from core.conversation import run_once
from core.registry import registry


def test_registry_resolves_core_toolset():
    builder.import_tool_modules()
    funcs = registry.resolve(["core"])
    names = {f.__name__ for f in funcs}
    assert "now_utc" in names
    assert "take_note" in names


def test_build_root_agent():
    agent = builder.build_agent("root")
    assert agent.name == "root"
    # core + self_dev + skills + delegate toolsets requested; at least core tools present.
    assert len(agent.tools) >= 2


def test_hot_reload_runs():
    status = builder.hot_reload()
    assert "registry_gen" in status
    assert isinstance(status["registry_gen"], int)


def test_root_agent_runs_against_local_llm():
    agent = builder.build_agent("root")
    out = asyncio.run(run_once(agent, "In one short sentence, what can you do?"))
    assert out and len(out) > 0
