"""Skill write-origin provenance (ported from Friday' tools/skill_provenance.py).

A single ContextVar distinguishes skills the agent created autonomously
(during a background self-improvement pass) from skills a user asked it to
create. The curator only ever auto-manages *agent-created* skills.

Reference: the reference implementation
"""

from __future__ import annotations

import contextvars

_write_origin: contextvars.ContextVar[str] = contextvars.ContextVar(
    "skill_write_origin",
    default="foreground",
)

BACKGROUND_REVIEW = "background_review"


def set_current_write_origin(origin: str) -> contextvars.Token[str]:
    """Bind the active write origin. Pass the returned token to reset()."""
    return _write_origin.set(origin or "foreground")


def reset_current_write_origin(token: contextvars.Token[str]) -> None:
    _write_origin.reset(token)


def get_current_write_origin() -> str:
    return _write_origin.get()


def is_background_review() -> bool:
    return get_current_write_origin() == BACKGROUND_REVIEW
