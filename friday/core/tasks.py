"""Background autonomous tasks (Manus-style).

Submit a high-level goal and the root agent runs it to completion *on the
server* — it keeps going after the user closes the browser. Each task records a
compact event log (tool calls/results) and the final output. State is persisted
so the task list survives restarts; a task still "running" when the process died
is marked "interrupted" on reload.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from core import audit
from core.config import settings

_TASKS: dict[str, dict[str, Any]] = {}
_MAX_EVENTS = 1000
_MAX_OUTPUT = 60_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store_path():
    return settings.home / "tasks.json"


def _persist() -> None:
    try:
        settings.ensure_home()
        _store_path().write_text(json.dumps(_TASKS, default=str, indent=2), encoding="utf-8")
    except OSError:
        pass


def _load() -> None:
    p = _store_path()
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for t in data.values():
        if t.get("status") == "running":
            t["status"] = "interrupted"  # the process that ran it is gone
    _TASKS.update(data)


_load()


def _summary(t: dict) -> dict:
    return {
        "id": t["id"],
        "goal": t["goal"],
        "status": t["status"],
        "created": t.get("created"),
        "finished": t.get("finished"),
        "error": t.get("error"),
        "events": len(t.get("events", [])),
        "tool_calls": sum(1 for e in t.get("events", []) if e.get("type") == "tool_call"),
    }


def list_tasks(limit: int = 50) -> list[dict]:
    items = sorted(_TASKS.values(), key=lambda t: t.get("created", ""), reverse=True)
    return [_summary(t) for t in items[:limit]]


def get_task(task_id: str) -> dict | None:
    return _TASKS.get(task_id)


def _parse_sse(chunk: str) -> list[dict]:
    out: list[dict] = []
    for line in chunk.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                out.append(json.loads(line[5:].strip()))
            except json.JSONDecodeError:
                pass
    return out


def _record(entry: dict, ev: dict) -> None:
    t = ev.get("type")
    if t == "token":
        entry["output"] = (entry["output"] + ev.get("text", ""))[:_MAX_OUTPUT]
    if t in ("start", "tool_call", "tool_result", "thinking_start", "thinking_end", "done"):
        log = entry["events"]
        log.append({k: ev.get(k) for k in ("type", "name", "ok", "id", "agent") if k in ev})
        if len(log) > _MAX_EVENTS:
            del log[: len(log) - _MAX_EVENTS]


async def _run(task_id: str, goal: str) -> None:
    from control_plane import builder
    from control_plane.streaming import stream_agent

    entry = _TASKS[task_id]
    try:
        async for chunk in stream_agent(
            lambda: builder.build_agent("root"),
            goal,
            agent_name="root",
            chat_id=f"task-{task_id}",
        ):
            for ev in _parse_sse(chunk):
                _record(entry, ev)
        entry["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        entry["status"] = "error"
        entry["error"] = f"{type(exc).__name__}: {exc}"
        audit.log("task.error", id=task_id, error=str(exc)[:200])
    finally:
        entry["finished"] = _now()
        _persist()
        audit.log("task.done", id=task_id, status=entry["status"])


def submit(goal: str) -> dict:
    """Create a background task for ``goal`` and start running it."""
    if not (goal or "").strip():
        raise ValueError("empty goal")
    task_id = uuid.uuid4().hex[:12]
    entry = {
        "id": task_id,
        "goal": goal.strip(),
        "status": "running",
        "created": _now(),
        "finished": None,
        "error": None,
        "output": "",
        "events": [],
    }
    _TASKS[task_id] = entry
    _persist()
    audit.log("task.submit", id=task_id, goal=goal[:200])
    try:
        asyncio.get_running_loop().create_task(_run(task_id, goal))
    except RuntimeError:
        # No running loop (e.g. called synchronously) — run to completion now.
        asyncio.run(_run(task_id, goal))
    return _summary(entry)
