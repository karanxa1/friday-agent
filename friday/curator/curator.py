"""Archive-only skill curator (inspired by the reference agent/curator.py).

A lightweight self-maintenance pass over *agent-created* skills:

* Pure staleness state-machine (no LLM): active -> stale -> archived based on
  idle time. Reactivation on use is handled in skills.usage.bump().
* Only touches skills with ``created_by == "agent"`` and ``pinned == False``.
* NEVER deletes -- the most destructive action is moving a skill directory into
  ``skills/.archive/`` (recoverable).
* A scheduler gate (interval + idle) decides when a run is due; state persists
  in ``skills/.curator_state``.

This is the "learn" stage of plan->act->measure->adapt->learn for procedural
memory.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from core import audit
from core.config import settings
from skills import usage

_LOCK = threading.RLock()

# Defaults (env-tunable later if needed); days expressed in seconds.
_DAY = 86400.0
STALE_AFTER = 30 * _DAY
ARCHIVE_AFTER = 90 * _DAY
INTERVAL = 7 * _DAY  # minimum gap between curator runs


def _state_path() -> Path:
    settings.ensure_home()
    return settings.skills_dir / ".curator_state"


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"last_run_at": 0.0, "run_count": 0, "paused": False}


def _save_state(state: dict[str, Any]) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(p)


def should_run_now(now: float | None = None) -> bool:
    """True if a curator run is due (enabled, not paused, interval elapsed)."""
    now = now if now is not None else time.time()
    state = _load_state()
    if state.get("paused"):
        return False
    last = float(state.get("last_run_at", 0.0))
    if last == 0.0:
        return False  # first observation seeds last_run_at without acting
    return (now - last) >= INTERVAL


def _archive_skill(name: str) -> bool:
    src = settings.skills_dir / name
    if not src.is_dir():
        return False
    dst = settings.archive_dir / name
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst = settings.archive_dir / f"{name}.{int(time.time())}"
    shutil.move(str(src), str(dst))
    return True


def apply_automatic_transitions(now: float | None = None) -> dict[str, list[str]]:
    """Pure staleness pass over agent-created, non-pinned skills.

    Returns a dict of {"staled": [...], "archived": [...]}.
    """
    now = now if now is not None else time.time()
    staled: list[str] = []
    archived: list[str] = []
    with _LOCK:
        entries = usage.all_entries()
        for name, info in entries.items():
            if info.get("created_by") != "agent" or info.get("pinned"):
                continue
            idle = now - float(info.get("last_activity_at", now))
            state = info.get("state", "active")
            if state == "active" and idle >= STALE_AFTER:
                usage.set_state(name, "stale")
                staled.append(name)
                state = "stale"
            if state == "stale" and idle >= ARCHIVE_AFTER:
                if _archive_skill(name):
                    usage.set_state(name, "archived")
                    archived.append(name)
    if staled or archived:
        audit.log("curator.transitions", staled=staled, archived=archived)
    return {"staled": staled, "archived": archived}


def run(force: bool = False, now: float | None = None) -> dict[str, Any]:
    """Run the curator if due (or forced). Records state + returns a report."""
    now = now if now is not None else time.time()
    state = _load_state()

    if state.get("last_run_at", 0.0) == 0.0 and not force:
        # First observation: seed the clock, don't act yet (reference behavior).
        state["last_run_at"] = now
        _save_state(state)
        audit.log("curator.seeded", at=now)
        return {"ran": False, "reason": "seeded_first_run", "staled": [], "archived": []}

    if not force and not should_run_now(now):
        return {"ran": False, "reason": "not_due", "staled": [], "archived": []}

    result = apply_automatic_transitions(now)
    state["last_run_at"] = now
    state["run_count"] = int(state.get("run_count", 0)) + 1
    _save_state(state)
    report = {"ran": True, "run_count": state["run_count"], **result}
    audit.log("curator.run", **report)
    return report


def pause(paused: bool = True) -> None:
    state = _load_state()
    state["paused"] = paused
    _save_state(state)


def status() -> dict[str, Any]:
    return _load_state()
