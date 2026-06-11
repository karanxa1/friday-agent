"""Persistent curated memory (inspired by the reference tools/memory_tool.py).

Two char-bounded markdown stores under ``~/.friday/memories/``:
  MEMORY.md -- the agent's own notes
  USER.md   -- facts about the user

Key design carried over: a *frozen snapshot* is loaded once and is what
would be injected into a system prompt; live edits persist to disk immediately
but do not mutate the snapshot mid-session (preserves prompt-cache stability).
Entries are delimited by ``\\n§\\n`` and matched for replace/remove by a short
unique substring (no ids).
"""

from __future__ import annotations

import threading
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool

_DELIM = "\n§\n"
_LIMITS = {"memory": 2200, "user": 1375}
_LOCK = threading.RLock()

# Frozen snapshot captured at first load (per process).
_snapshot: dict[str, str] = {}


def _file(kind: str) -> Path:
    settings.ensure_home()
    name = "MEMORY.md" if kind == "memory" else "USER.md"
    return settings.memories_dir / name


def _read(kind: str) -> str:
    p = _file(kind)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _write(kind: str, text: str) -> None:
    p = _file(kind)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def _entries(text: str) -> list[str]:
    return [e.strip() for e in text.split(_DELIM) if e.strip()]


def load_snapshot() -> dict[str, str]:
    """Capture the frozen snapshot of both stores (idempotent per process)."""
    with _LOCK:
        if not _snapshot:
            _snapshot["memory"] = _read("memory")
            _snapshot["user"] = _read("user")
    return dict(_snapshot)


def snapshot_for_prompt() -> str:
    """Return the frozen snapshot formatted for system-prompt injection."""
    snap = load_snapshot()
    out = []
    if snap.get("memory"):
        out.append("## Memory\n" + snap["memory"])
    if snap.get("user"):
        out.append("## About the user\n" + snap["user"])
    return "\n\n".join(out)


def _add(kind: str, entry: str) -> str:
    entry = entry.strip()
    if not entry:
        return "error: empty entry"
    with _LOCK:
        text = _read(kind)
        entries = _entries(text)
        entries.append(entry)
        new = _DELIM.join(entries)
        if len(new) > _LIMITS[kind]:
            return (
                f"error: {kind} store would exceed {_LIMITS[kind]} chars; "
                "consolidate or remove an entry first"
            )
        _write(kind, new)
    audit.log("memory.add", kind=kind, chars=len(entry))
    return f"added to {kind} ({len(entry)} chars)"


@tool("memory", description="Add a note to the agent's long-term memory (MEMORY.md).")
def memory_add(entry: str) -> str:
    """Record a durable note in MEMORY.md.

    Args:
        entry: the note to remember.
    """
    return _add("memory", entry)


@tool("memory", description="Add a fact about the user to USER.md.")
def user_add(entry: str) -> str:
    """Record a durable fact about the user in USER.md.

    Args:
        entry: the fact to remember.
    """
    return _add("user", entry)


@tool("memory", description="Remove a memory entry by a short unique substring match.")
def memory_remove(match: str, kind: str = "memory") -> str:
    """Remove an entry containing ``match`` from MEMORY.md or USER.md.

    Args:
        match: a short unique substring of the entry to remove.
        kind: "memory" (default) or "user".
    """
    if kind not in _LIMITS:
        return "error: kind must be 'memory' or 'user'"
    with _LOCK:
        entries = _entries(_read(kind))
        keep = [e for e in entries if match not in e]
        if len(keep) == len(entries):
            return f"no {kind} entry matched {match!r}"
        _write(kind, _DELIM.join(keep))
    audit.log("memory.remove", kind=kind, match=match[:60])
    return f"removed {len(entries) - len(keep)} {kind} entry(ies)"


@tool("memory", description="Show current long-term memory (live, not the frozen snapshot).")
def memory_show() -> str:
    """Return the live contents of MEMORY.md and USER.md."""
    return f"=== MEMORY.md ===\n{_read('memory')}\n\n=== USER.md ===\n{_read('user')}"
