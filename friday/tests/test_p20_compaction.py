"""P20: context compression — token estimate, threshold, summarize old turns."""

from __future__ import annotations

import asyncio

import pytest
from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from core import compaction
from core.model import make_llm


@pytest.fixture(autouse=True)
def _restore_settings():
    """Snapshot the frozen settings we mutate and restore them after each test.

    Mutate the SAME object ``compaction`` holds (``compaction.settings``): other
    tests reload ``core.config``, which swaps the module-level singleton, so a
    fresh ``from core.config import settings`` here could be a different object
    than the one compaction.py captured at import.
    """
    s = compaction.settings
    saved = (s.context_limit, s.compact_keep)
    yield
    object.__setattr__(s, "context_limit", saved[0])
    object.__setattr__(s, "compact_keep", saved[1])


async def _build_and_compact(n: int):
    """Build a session with n events and run maybe_compact in ONE loop.

    Doing build + compact inside a single ``asyncio.run`` avoids cross-loop
    issues with the InMemory session service under ``asyncio_mode=auto``.
    """
    agent = LlmAgent(name="t", model=make_llm("easy"), instruction="hi", tools=[])
    runner = InMemoryRunner(agent=agent, app_name="x")
    session = await runner.session_service.create_session(app_name="x", user_id="u")
    for i in range(n):
        ev = Event(
            author="user" if i % 2 == 0 else "assistant",
            content=types.Content(
                role="user" if i % 2 == 0 else "model",
                parts=[types.Part(text=f"Message {i}: " + ("filler content to add tokens. " * 8))],
            ),
        )
        await runner.session_service.append_event(session, ev)
    info = await compaction.maybe_compact(runner, session.id, user_id="u", app_name="x")
    live = compaction._live_session(runner, "x", "u", session.id)
    return info, live


def test_estimate_tokens_monotonic():
    e1 = [Event(author="user", content=types.Content(role="user", parts=[types.Part(text="x" * 400)]))]
    e2 = [Event(author="user", content=types.Content(role="user", parts=[types.Part(text="x" * 4000)]))]
    assert compaction.estimate_tokens(e2) > compaction.estimate_tokens(e1)
    assert compaction.estimate_tokens([]) == 0


async def test_no_compaction_under_limit():
    object.__setattr__(compaction.settings, "context_limit", 10_000_000)
    info, _ = await _build_and_compact(8)
    assert info is None  # well under the limit


async def test_compaction_triggers_and_summarizes(monkeypatch):
    object.__setattr__(compaction.settings, "context_limit", 150)
    object.__setattr__(compaction.settings, "compact_keep", 40)

    # Stub the LLM summary so the test is deterministic (no live model call).
    async def _fake_summary(_transcript: str) -> str:
        return "## Goal\nTest goal.\n\n## Progress\nDid things."

    monkeypatch.setattr(compaction, "_summarize", _fake_summary)

    info, live = await _build_and_compact(12)
    assert info is not None
    assert info["summarized"] >= 1
    assert info["kept"] >= 1
    first_text = live.events[0].content.parts[0].text or ""
    assert "CONVERSATION SUMMARY" in first_text
    assert len(live.events) < 12


async def test_disabled_when_limit_zero():
    object.__setattr__(compaction.settings, "context_limit", 0)
    info, _ = await _build_and_compact(12)
    assert info is None
