"""Built-in native tools for the ``core`` toolset.

Kept deliberately small. Other toolsets (self_dev, skills, delegate, ...)
register their own tools in their packages and are imported by the builder.
"""

from __future__ import annotations

import datetime as _dt

from core.registry import tool


@tool("core", description="Return the current UTC date and time as an ISO-8601 string.")
def now_utc() -> str:
    """Get the current UTC timestamp (ISO-8601)."""
    return _dt.datetime.now(_dt.UTC).isoformat()


@tool("core", description="Echo a short note into the audit log and return confirmation.")
def take_note(note: str) -> str:
    """Record a short free-text note for later reference.

    Args:
        note: The text to remember in this run's audit trail.
    """
    from core import audit

    audit.log("tool.take_note", note=note[:500])
    return f"noted: {note[:200]}"


@tool("core", description="List every available tool grouped by toolset, with descriptions.")
def list_all_tools(query: str = "") -> str:
    """Discover available tools (ported from the reference tool_search).

    Args:
        query: optional case-insensitive filter on tool name or description.
    """
    from core.registry import registry

    q = query.lower().strip()
    by_set: dict[str, list[str]] = {}
    for entry in registry.list():
        if q and q not in entry.name.lower() and q not in entry.description.lower():
            continue
        by_set.setdefault(entry.toolset, []).append(f"  {entry.name} — {entry.description}")
    if not by_set:
        return f"(no tools match {query!r})"
    out = []
    for ts in sorted(by_set):
        out.append(f"[{ts}]")
        out.extend(sorted(by_set[ts]))
    return "\n".join(out)
