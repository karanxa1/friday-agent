"""Thin async helper to run an ADK agent for a single user message.

Used by tests, the CLI, sub-agent spawning, and the control plane.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from core import audit


async def run_once(agent: LlmAgent, user_text: str, *, user_id: str = "u", app_name: str = "friday") -> str:
    """Run ``agent`` on ``user_text`` and return the concatenated text output."""
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id=user_id)
    msg = types.Content(role="user", parts=[types.Part(text=user_text)])
    out_parts: list[str] = []
    tool_calls = 0
    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=msg):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if getattr(part, "function_call", None):
                    tool_calls += 1
                    audit.log(
                        "run.tool_call",
                        agent=agent.name,
                        tool=part.function_call.name,
                    )
                if getattr(part, "text", None):
                    out_parts.append(part.text)
    text = "".join(out_parts).strip()
    audit.log("run.complete", agent=agent.name, tool_calls=tool_calls, chars=len(text))
    return text
