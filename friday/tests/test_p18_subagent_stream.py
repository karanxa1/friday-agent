"""P18: sub-agent streaming + full toolset access.

Regression tests for the "I can't see sub-agent tasks" fix: spawning a child
must (a) grant it the full toolset (so it isn't crippled like the old leaf set
that lacked run_command/read_file), and (b) when a parent stream is forwarding,
emit the child's activity as depth-tagged ``subagent_start`` … ``subagent_end``
events with the child's tool calls nested inside.
"""

from __future__ import annotations

import asyncio

from control_plane import builder


def test_subagent_has_full_toolset():
    from delegate.spawn import _child_toolsets

    builder.import_tool_modules()
    ts = _child_toolsets()
    # The old crippled leaf set was {core, skills, search, vision, metrics, web}
    # and broke when the child reached for run_command/read_file. Now it's full.
    for needed in ("system", "files", "self_dev", "delegate", "sandbox"):
        assert needed in ts, f"sub-agent missing {needed!r}"
    # scheduler-owned toolset stays out of a one-shot child
    assert "automations" not in ts


def test_subagent_resolves_run_command_and_read_file():
    from core.registry import registry
    from delegate.spawn import _child_toolsets

    builder.import_tool_modules()
    tools = registry.resolve(_child_toolsets())
    names = {t.__name__ for t in tools}
    assert "run_command" in names
    assert "read_file" in names


def test_stream_child_emits_nested_events():
    """A real child run forwards depth-tagged start/end + nested tool events."""
    from google.adk.agents import LlmAgent

    from control_plane.streaming import stream_child
    from core.model import make_llm
    from core.registry import registry
    from delegate.spawn import _child_toolsets

    builder.import_tool_modules()
    tools = registry.resolve(_child_toolsets())
    child = LlmAgent(
        name="sub_leaf_1",
        model=make_llm("easy"),  # type: ignore[arg-type]
        description="test child",
        instruction=(
            "You are a leaf sub-agent. Use run_command to execute exactly "
            "`echo STREAM_OK`, then report the output."
        ),
        tools=tools,
    )

    async def run() -> list[dict]:
        sink: asyncio.Queue = asyncio.Queue()
        result = await stream_child(child, "Run echo STREAM_OK and report it.", sink=sink, depth=1)
        events = []
        while not sink.empty():
            events.append(sink.get_nowait())
        events.append({"type": "_final", "text": result})
        return events

    events = asyncio.run(run())
    types = [e["type"] for e in events]
    assert types[0] == "subagent_start"
    assert "subagent_end" in types
    # start before end, both at depth 1
    assert events[0]["depth"] == 1
    # every forwarded event carries depth >= 1 (never leaks as a root event)
    for e in events:
        if e["type"] in ("_final",):
            continue
        assert e.get("depth", 0) >= 1, f"event leaked without depth: {e['type']}"
    # the child actually ran the command (saw a run_command tool_call)
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert any(e["name"] == "run_command" for e in tool_calls)


def test_spawn_falls_back_to_run_once_without_sink():
    """No parent stream → quiet run returning just the summary (CLI/tests)."""
    import delegate.spawn as sp

    builder.import_tool_modules()
    out = asyncio.run(sp.spawn_subagent("Reply with exactly: NOSINK", force_tier="easy"))
    assert out and "error" not in out.lower()[:20]
