"""P17: thinking config on the model factory + reserved tool-name guard.

Regression tests for the "no thinking stream in the UI" bug: the local
Anthropic-protocol endpoint only emits reasoning when the request carries
``thinking={...}`` AND ``allowed_openai_params=['thinking']`` (litellm drops it
otherwise), and a tool named ``web_search`` (a provider built-in) silently
disables thinking. Both are asserted here so neither regresses.
"""

from __future__ import annotations

import pytest


def test_make_llm_enables_thinking_passthrough():
    from core.model import make_llm

    llm = make_llm("hard", thinking=True)
    args = llm._additional_args
    assert "thinking" in args, "thinking param must be forwarded to litellm"
    assert args["thinking"]["type"] == "enabled"
    assert args["thinking"]["budget_tokens"] > 0
    # litellm drops unknown params under drop_params=true unless explicitly allowed
    assert "thinking" in (args.get("allowed_openai_params") or []), (
        "allowed_openai_params must include 'thinking' or litellm strips it"
    )
    assert args.get("max_tokens", 0) > 0


def test_make_llm_thinking_off_omits_param():
    from core.model import make_llm

    llm = make_llm("easy", thinking=False)
    assert "thinking" not in llm._additional_args


def test_make_llm_thinking_uses_thinking_model_variant():
    from core.model import make_llm

    llm = make_llm("hard", thinking=True)
    assert llm.model.endswith("-thinking")


def test_reserved_tool_names_includes_web_search():
    from control_plane.builder import RESERVED_TOOL_NAMES

    # web_search collides with Anthropic's server-side built-in and disables
    # thinking — it must stay on the reserved list so the guard warns.
    assert "web_search" in RESERVED_TOOL_NAMES


def test_no_registered_tool_uses_reserved_name():
    from control_plane import builder
    from control_plane.builder import RESERVED_TOOL_NAMES
    from core.registry import registry

    builder.import_tool_modules()
    native_names = {e.name for e in registry.list()}
    collisions = native_names & RESERVED_TOOL_NAMES
    assert not collisions, (
        f"native tools collide with provider built-ins (disables thinking): {collisions}"
    )


def test_callmissed_tool_renamed_to_search_web():
    # The MCP search tool must NOT be named web_search.
    import mcp_tools.callmissed_search_server as srv

    assert hasattr(srv, "search_web")
    assert not hasattr(srv, "web_search")
