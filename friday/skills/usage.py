"""Per-skill usage telemetry sidecar (inspired by Friday' tools/skill_usage.py).

Stored as JSON at ``<skills_dir>/.usage.json``. Tracks, per skill:
use_count, view_count, patch_count, last_activity_at, state, pinned,
created_by ("agent" | "user").

The curator reads ``state`` + ``created_by`` + ``pinned`` to decide which
skills it may auto-archive.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Literal

from core.config import settings

_LOCK = threading.RLock()

State = Literal["active", "stale", "archived"]


def _path():
    return settings.skills_dir / ".usage.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict[str, Any]) -> None:
    settings.ensure_home()
    p = _path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _entry(data: dict[str, Any], name: str) -> dict[str, Any]:
    return data.setdefault(
        name,
        {
            "use_count": 0,
            "view_count": 0,
            "patch_count": 0,
            "last_activity_at": time.time(),
            "state": "active",
            "pinned": False,
            "created_by": "user",
        },
    )


def mark_created(name: str, *, by: str) -> None:
    with _LOCK:
        data = _load()
        e = _entry(data, name)
        e["created_by"] = by
        e["last_activity_at"] = time.time()
        _save(data)


def bump(name: str, field: str) -> None:
    with _LOCK:
        data = _load()
        e = _entry(data, name)
        if field in ("use_count", "view_count", "patch_count"):
            e[field] = int(e.get(field, 0)) + 1
        e["last_activity_at"] = time.time()
        if e.get("state") == "stale":
            e["state"] = "active"  # reactivate on use
        _save(data)


def set_state(name: str, state: State) -> None:
    with _LOCK:
        data = _load()
        e = _entry(data, name)
        e["state"] = state
        e["last_activity_at"] = time.time()
        _save(data)


def set_pinned(name: str, pinned: bool) -> None:
    with _LOCK:
        data = _load()
        _entry(data, name)["pinned"] = pinned
        _save(data)


def forget(name: str) -> None:
    with _LOCK:
        data = _load()
        if name in data:
            del data[name]
            _save(data)


def get(name: str) -> dict[str, Any] | None:
    with _LOCK:
        return _load().get(name)


def all_entries() -> dict[str, Any]:
    with _LOCK:
        return _load()
