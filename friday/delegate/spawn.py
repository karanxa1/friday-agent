"""Recursive sub-agent spawning (inspired by the reference tools/delegate_tool.py).

``spawn_subagent`` lets any agent decompose work: it classifies the task
(easy->Sonnet, hard->Opus unless ``force_tier`` given), builds a child agent
with the FULL toolset, runs it (streaming its work to the UI when a parent
stream is forwarding, else quietly), and returns the child's final summary.

Guards against runaway fan-out:
  * Depth cap (``max_spawn_depth``, ContextVar) bounds recursion *depth*.
  * Per-turn breadth cap (``max_fanout``, ContextVar) bounds how many children
    a single agent spawns, so a child told "don't ask, just do it" can't fork
    a swarm. Both are required because depth alone allows N^depth agents.

Reference: the reference implementation
"""

from __future__ import annotations

import contextvars

from google.adk.agents import LlmAgent

from core import audit
from core.config import settings
from core.model import classify_difficulty, make_llm
from core.registry import registry

# Tracks recursion depth across the async call chain.
_depth: contextvars.ContextVar[int] = contextvars.ContextVar("spawn_depth", default=0)
# Tracks how many children the CURRENT agent has spawned this turn (breadth cap).
_fanout: contextvars.ContextVar[int] = contextvars.ContextVar("spawn_fanout", default=0)

# Sub-agents get FULL capability — every toolset the registry knows about,
# including further delegation. Sensitive actions (self-edit, capability,
# credentials, publishing) still pass through the human-approval queue, so
# "access to everything" stays safe.
_NEVER = {"automations"}  # scheduler-owned; not meaningful inside a one-shot child


def current_depth() -> int:
    return _depth.get()


def _child_toolsets() -> list[str]:
    """The child's toolsets — everything available except scheduler-owned ones."""
    return sorted(registry.toolsets() - _NEVER)


async def _spawn_subagent_impl(
    task: str,
    role: str = "leaf",
    context: str = "",
    force_tier: str = "",
) -> str:
    """Spawn a constrained child agent to handle a focused sub-task.

    Args:
        task: the goal for the child agent.
        role: "leaf" (default, cannot delegate) or "orchestrator" (may delegate).
        context: optional background passed to the child.
        force_tier: "easy" or "hard" to override automatic difficulty routing.

    Returns:
        The child's final text output (summary only).
    """
    from core.conversation import run_once  # local import to avoid cycle

    depth = _depth.get()
    if depth >= settings.max_spawn_depth:
        audit.log("spawn.depth_exceeded", depth=depth, max=settings.max_spawn_depth)
        return f"error: max spawn depth ({settings.max_spawn_depth}) reached; cannot delegate further"

    # Breadth cap: how many children THIS agent has already spawned this turn.
    used = _fanout.get()
    if used >= settings.max_fanout:
        audit.log("spawn.fanout_exceeded", used=used, max=settings.max_fanout, depth=depth)
        return (
            f"error: fan-out limit ({settings.max_fanout}) reached for this agent; "
            f"do the remaining work yourself or consolidate sub-tasks"
        )
    _fanout.set(used + 1)

    tier = force_tier if force_tier in ("easy", "hard") else classify_difficulty(task)
    toolsets = _child_toolsets()
    tools = registry.resolve(toolsets)
    # Every child can delegate further (bounded by depth + breadth caps), so
    # deep work decomposes naturally — full capability, recursively.
    if spawn_subagent not in tools:
        tools = [*tools, spawn_subagent]

    instruction = (
        f"You are a focused {role} sub-agent. Complete exactly this task and "
        f"return a concise result. Do not ask clarifying questions; make "
        f"reasonable assumptions. You have the full toolset and may delegate "
        f"further if it genuinely helps.\n\nTask: {task}"
    )
    if context:
        instruction += f"\n\nContext: {context}"

    child = LlmAgent(
        name=f"sub_{role}_{depth + 1}",
        model=make_llm(tier),  # type: ignore[arg-type]
        description=f"{role} sub-agent at depth {depth + 1}",
        instruction=instruction,
        tools=tools,
    )

    audit.log("spawn.start", role=role, tier=tier, depth=depth + 1, toolsets=toolsets, task=task[:200])
    # The child starts its OWN fan-out budget at 0 (the breadth cap is per
    # agent, not global), while inheriting the deeper recursion level.
    dtoken = _depth.set(depth + 1)
    ftoken = _fanout.set(0)
    try:
        # If a parent stream is forwarding (web UI), stream the child's thinking
        # and tool calls so the user watches the sub-agent work live. Otherwise
        # (CLI/tests) fall back to a quiet run that returns just the summary.
        from control_plane.streaming import stream_child, subagent_sink

        sink = subagent_sink()
        if sink is not None:
            result = await stream_child(
                child, task, sink=sink, depth=depth + 1, tier=tier, role=role
            )
        else:
            result = await run_once(child, task, app_name="friday-sub")
    finally:
        _depth.reset(dtoken)
        _fanout.reset(ftoken)
    audit.log("spawn.done", role=role, depth=depth + 1, chars=len(result))
    return result or "(sub-agent returned no output)"


# Expose as a plain function so ADK auto-wraps it as a FunctionTool.
async def spawn_subagent(task: str, role: str = "leaf", context: str = "", force_tier: str = "") -> str:
    """Delegate a focused sub-task to a constrained child agent (returns its summary)."""
    return await _spawn_subagent_impl(task=task, role=role, context=context, force_tier=force_tier)


# Register into the 'delegate' toolset.
registry.register(spawn_subagent, toolset="delegate", description="Delegate a sub-task to a constrained child agent.")
