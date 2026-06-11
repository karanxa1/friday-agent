"""Context compression — summarize old conversation turns to fit the window.

Long sessions eventually overflow the model's context. Rather than truncating
(which loses information) we *compact*: an auxiliary cheap-model call summarizes
the older events into a fixed Markdown brief (Goal / Constraints / Progress /
Decisions / Next Steps / Critical Context / Relevant Files), and the most recent
events are kept verbatim. The old events are replaced by a single synthetic
"summary" user turn so the agent retains the thread without the token cost.

Pattern adapted from opencode's ``core/src/session/compaction.ts`` and
the reference agent's context compressor. Triggered before a turn when the estimated
token count exceeds ``settings.context_limit``.
"""

from __future__ import annotations

from typing import Any

from google.adk.events import Event
from google.genai import types

from core import audit
from core.config import settings

# Rough token estimate: ~4 chars/token for English+code. Cheap and good enough
# to decide *when* to compact (we don't need exact provider accounting).
_CHARS_PER_TOKEN = 4

_SUMMARY_PROMPT = """You are compacting a long agent\u2013user conversation so it fits the context window without losing what matters. Read the transcript below and produce a faithful, information-dense brief using EXACTLY these Markdown sections:

## Goal
The user's overall objective(s) in this conversation.

## Constraints & Preferences
Hard requirements, preferences, conventions, and decisions the user stated.

## Progress
What has actually been done so far (files created/edited, tools run, results).

## Key Decisions
Important choices made and why.

## Next Steps
What remains to be done.

## Critical Context
Facts, values, names, IDs, errors, or state that must not be forgotten.

## Relevant Files
Paths touched or referenced, each with a one-line note.

Be concrete and specific (keep real paths, names, numbers, error strings). Do NOT invent anything. Omit a section only if truly empty. This brief REPLACES the older transcript, so anything you drop is lost.

--- TRANSCRIPT START ---
{transcript}
--- TRANSCRIPT END ---"""


def _event_text(ev: Event) -> str:
    """Flatten an event's parts to plain text for estimation/summarization."""
    out: list[str] = []
    content = getattr(ev, "content", None)
    parts = getattr(content, "parts", None) if content else None
    for p in parts or []:
        if getattr(p, "text", None):
            out.append(p.text)
        fc = getattr(p, "function_call", None)
        if fc is not None:
            out.append(f"[tool_call {getattr(fc, 'name', '?')}({dict(fc.args) if fc.args else {}})]")
        fr = getattr(p, "function_response", None)
        if fr is not None:
            out.append(f"[tool_result {getattr(fr, 'name', '?')}: {str(getattr(fr, 'response', ''))[:500]}]")
    return "\n".join(out)


def estimate_tokens(events: list[Event]) -> int:
    """Rough token estimate across a session's events."""
    chars = sum(len(_event_text(ev)) for ev in events)
    return chars // _CHARS_PER_TOKEN


def _author_label(ev: Event) -> str:
    return "User" if getattr(ev, "author", "") == "user" else "Assistant"


def _split_keep_recent(events: list[Event], keep_tokens: int) -> tuple[list[Event], list[Event]]:
    """Split events into (old, recent) where recent is ~keep_tokens from the end.

    Always keeps at least the final user turn intact. Never splits in a way that
    leaves the recent half empty.
    """
    recent: list[Event] = []
    budget = keep_tokens
    for ev in reversed(events):
        cost = max(1, len(_event_text(ev)) // _CHARS_PER_TOKEN)
        if budget - cost < 0 and recent:
            idx = len(events) - len(recent)
            return events[:idx], list(reversed(recent))
        recent.append(ev)
        budget -= cost
    return [], events


def _live_session(runner: Any, app_name: str, user_id: str, session_id: str):
    """Return the LIVE stored session object (not a copy).

    ``session_service.get_session`` returns a deep copy, so mutating it does not
    affect the conversation. The InMemory service keeps the real objects in a
    nested dict; reach in so our event-list rewrite actually takes effect.
    """
    svc = runner.session_service
    store = getattr(svc, "sessions", None)
    try:
        return store[app_name][user_id][session_id]  # type: ignore[index]
    except (KeyError, TypeError):
        return None


async def maybe_compact(
    runner: Any,
    session_id: str,
    *,
    user_id: str = "u",
    app_name: str = "friday",
) -> dict[str, Any] | None:
    """Compact the session if it exceeds the context limit. Returns a summary
    of what happened (for a UI event), or None if no compaction was needed.

    Rebuilds the session's event list as: [synthetic summary user-turn] +
    [recent events kept verbatim]. Uses the easy-tier model for the summary.
    """
    limit = settings.context_limit
    if limit <= 0:
        return None

    session = _live_session(runner, app_name, user_id, session_id)
    if session is None:
        return None
    events = list(session.events or [])
    before = estimate_tokens(events)
    if before < limit or len(events) < 6:
        return None

    old, recent = _split_keep_recent(events, settings.compact_keep)
    if not old:
        return None  # nothing old enough to summarize

    transcript = "\n\n".join(f"{_author_label(ev)}: {_event_text(ev)}" for ev in old if _event_text(ev))
    if not transcript.strip():
        return None

    # Summarize with the cheap tier via a throwaway one-shot agent.
    summary = await _summarize(transcript)
    if not summary or summary.startswith("error"):
        audit.log("compaction.skipped", reason="summary_failed", tokens=before)
        return None

    summary_text = (
        "[CONVERSATION SUMMARY — earlier turns were compacted to save context. "
        "Treat the following as established prior context.]\n\n" + summary
    )
    new_events = [
        Event(
            author="user",
            content=types.Content(role="user", parts=[types.Part(text=summary_text)]),
        ),
        *recent,
    ]
    # Replace the session's events in place (InMemory session stores a list).
    session.events.clear()
    session.events.extend(new_events)

    after = estimate_tokens(new_events)
    audit.log(
        "compaction.done",
        tokens_before=before,
        tokens_after=after,
        summarized_events=len(old),
        kept_events=len(recent),
    )
    return {
        "tokens_before": before,
        "tokens_after": after,
        "summarized": len(old),
        "kept": len(recent),
    }


async def _summarize(transcript: str) -> str:
    """Run the easy-tier model once to produce the compaction brief."""
    from google.adk.agents import LlmAgent

    from core.conversation import run_once
    from core.model import make_llm

    # Cap transcript size so the summary call itself can't overflow.
    max_chars = 120_000
    if len(transcript) > max_chars:
        transcript = transcript[-max_chars:]

    agent = LlmAgent(
        name="compactor",
        model=make_llm("easy"),  # type: ignore[arg-type]
        description="Summarizes old conversation turns into a compact brief.",
        instruction="You compress conversations faithfully and concisely.",
        tools=[],
    )
    try:
        return await run_once(agent, _SUMMARY_PROMPT.format(transcript=transcript), app_name="friday-compact")
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
