"""Recall tools (ported from the reference ``session_search_tool`` + ``memory_tool``).

Searches across everything Friday remembers: memory files (MEMORY.md /
USER.md), skill content, workspace files, and the audit trail.
"""

from __future__ import annotations

import json

from core import audit
from core.config import settings
from core.registry import tool


def _grep_file(path, query: str, source: str, hits: list[str], limit: int) -> None:
    if len(hits) >= limit or not path.is_file():
        return
    try:
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if query in line.lower():
                hits.append(f"[{source}:{n}] {line.strip()[:200]}")
                if len(hits) >= limit:
                    return
    except OSError:
        pass


@tool("recall", description="Search memory, skills, workspace files, and notes for a phrase.")
def recall_search(query: str, limit: int = 12) -> str:
    """Case-insensitive search across Friday's persistent stores.

    Args:
        query: phrase to look for.
        limit: maximum number of matching lines to return.
    """
    q = query.lower().strip()
    if not q:
        return "error: empty query"
    hits: list[str] = []
    home = settings.ensure_home()

    for name in ("MEMORY.md", "USER.md"):
        _grep_file(settings.memories_dir / name, q, f"memory/{name}", hits, limit)
    for skill_dir in sorted(settings.skills_dir.iterdir()) if settings.skills_dir.exists() else []:
        if skill_dir.name.startswith("."):
            continue
        _grep_file(skill_dir / "SKILL.md", q, f"skill/{skill_dir.name}", hits, limit)
    ws = home / "workspace"
    if ws.exists():
        for f in sorted(ws.rglob("*")):
            if f.is_file() and f.suffix in (".md", ".txt", ".json", ".py", ".csv"):
                _grep_file(f, q, f"workspace/{f.relative_to(ws)}", hits, limit)

    # Notes recorded via take_note live in the audit trail.
    audit_file = settings.logs_dir / "audit.jsonl"
    if audit_file.is_file() and len(hits) < limit:
        try:
            for raw in audit_file.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                note = str(entry.get("note", ""))
                if note and q in note.lower():
                    hits.append(f"[note] {note[:200]}")
                    if len(hits) >= limit:
                        break
        except OSError:
            pass

    audit.log("recall.search", query=query[:120], hits=len(hits))
    return "\n".join(hits) if hits else f"(no matches for {query!r})"


@tool("recall", description="Show recent agent activity from the audit trail.")
def recent_activity(limit: int = 20, prefix: str = "") -> str:
    """Summarize recent audit events (tool calls, runs, edits).

    Args:
        limit: number of events to show (newest last).
        prefix: optional event-name prefix filter, e.g. 'run.' or 'skill.'.
    """
    events = audit.recent(limit=limit, event_prefix=prefix or None)
    if not events:
        return "(no recent activity)"
    rows = []
    for e in events:
        extras = {k: v for k, v in e.items() if k not in ("id", "ts", "event")}
        detail = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(extras.items())[:4])
        rows.append(f"{e['event']}  {detail}")
    return "\n".join(rows)
