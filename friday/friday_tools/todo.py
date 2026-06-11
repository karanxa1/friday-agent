"""Todo tools (ported from the reference ``tools/todo_tool.py``).

A simple persistent task list at ``~/.friday/todos.json`` so the agent can
plan multi-step work and tick items off as it goes.
"""

from __future__ import annotations

import json
import threading

from core import audit
from core.config import settings
from core.registry import tool

_LOCK = threading.Lock()


def _path():
    settings.ensure_home()
    return settings.home / "todos.json"


def _load() -> list[dict]:
    p = _path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return []


def _save(items: list[dict]) -> None:
    _path().write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _render(items: list[dict]) -> str:
    if not items:
        return "(no todos)"
    return "\n".join(
        f"[{'x' if t['done'] else ' '}] #{t['id']} {t['task']}" for t in items
    )


@tool("todo", description="Add a task to the persistent todo list.")
def todo_add(task: str) -> str:
    """Add a todo item.

    Args:
        task: short description of the task.
    """
    with _LOCK:
        items = _load()
        next_id = max((t["id"] for t in items), default=0) + 1
        items.append({"id": next_id, "task": task[:500], "done": False})
        _save(items)
    audit.log("todo.add", id=next_id, task=task[:120])
    return f"added todo #{next_id}: {task[:120]}"


@tool("todo", description="List all todos with their ids and completion state.")
def todo_list() -> str:
    """Show the current todo list."""
    with _LOCK:
        return _render(_load())


@tool("todo", description="Mark a todo item as done by id.")
def todo_done(todo_id: int) -> str:
    """Mark a todo complete.

    Args:
        todo_id: the numeric id shown by todo_list.
    """
    with _LOCK:
        items = _load()
        for t in items:
            if t["id"] == todo_id:
                t["done"] = True
                _save(items)
                audit.log("todo.done", id=todo_id)
                return f"completed todo #{todo_id}: {t['task'][:120]}"
    return f"error: todo #{todo_id} not found"


@tool("todo", description="Remove completed items (or one item by id) from the todo list.")
def todo_clear(todo_id: int = 0) -> str:
    """Clear todos.

    Args:
        todo_id: a specific id to remove, or 0 to remove all completed items.
    """
    with _LOCK:
        items = _load()
        if todo_id:
            kept = [t for t in items if t["id"] != todo_id]
            if len(kept) == len(items):
                return f"error: todo #{todo_id} not found"
        else:
            kept = [t for t in items if not t["done"]]
        _save(kept)
    removed = len(items) - len(kept)
    audit.log("todo.clear", removed=removed)
    return f"removed {removed} todo(s); {len(kept)} remaining"
