"""Human-approval queue (inspired by Friday' write_approval / approval gate).

Sensitive actions (self-edit, new MCP/tool, publish, ad-spend, new auth) are
not executed inline. They are *staged* as pending actions; a human approves or
rejects them via the control-plane UI/CLI. Approved actions are then applied by
the caller.

The autonomy level (settings.autonomy) controls behavior:
  L0  -> everything staged, nothing auto-applies (suggest only)
  L1  -> sensitive actions staged for approval (default)
  L2  -> whitelisted action types auto-approve; the rest still staged
  L3  -> full-auto: every action auto-approves, NO human approval (operator
         opt-in; only safe on a single-user, network-locked host)
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Literal

from core import audit
from core.config import settings

Status = Literal["pending", "approved", "rejected", "applied"]

_LOCK = threading.RLock()
_QUEUE: dict[str, dict[str, Any]] = {}

# The real action types submitted by the codebase (see submit() callers).
ACTION_TYPES = frozenset({"self_edit", "self_revert", "capability", "credential"})

# Action types that may auto-approve at autonomy L2. Deliberately empty: every
# gated action (self-edit, self-revert, capability authoring) is dangerous
# enough to stage even in autonomous mode. Any entry added here MUST be a member
# of ACTION_TYPES (asserted in tests) so a typo can't silently disable a gate.
_L2_WHITELIST: frozenset[str] = frozenset()


def _store_path():
    return settings.home / "approvals.json"


def _persist() -> None:
    try:
        settings.ensure_home()
        _store_path().write_text(json.dumps(_QUEUE, indent=2, default=str), encoding="utf-8")
    except OSError:
        pass


def _load() -> None:
    p = _store_path()
    if p.is_file():
        try:
            _QUEUE.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass


_load()


def gate(action_type: str) -> bool:
    """Return True if an action of this type may auto-proceed without staging.

    L3 ("full-auto") auto-approves EVERY action — no human approval at all.
    This is an explicit operator opt-in for a single-user, network-locked
    deployment; it removes all safety gates, so the host must not be exposed
    beyond the operator. L2 auto-approves only whitelisted types; L0/L1 always
    stage sensitive actions.
    """
    level = settings.autonomy.upper()
    if level == "L3":
        return True
    if level == "L2" and action_type in _L2_WHITELIST:
        return True
    return False  # L0 and L1 always stage sensitive actions


def submit(action_type: str, summary: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stage a pending action. Returns the queue entry (with id + status)."""
    if gate(action_type):
        entry = {
            "id": uuid.uuid4().hex[:12],
            "type": action_type,
            "summary": summary,
            "payload": payload or {},
            "status": "approved",
            "ts": time.time(),
            "auto": True,
        }
        audit.log("approval.auto", id=entry["id"], type=action_type, summary=summary[:200])
    else:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "type": action_type,
            "summary": summary,
            "payload": payload or {},
            "status": "pending",
            "ts": time.time(),
            "auto": False,
        }
        audit.log("approval.submit", id=entry["id"], type=action_type, summary=summary[:200])
    with _LOCK:
        _QUEUE[entry["id"]] = entry
        _persist()
    return entry


def decide(action_id: str, approve: bool) -> dict[str, Any] | None:
    with _LOCK:
        entry = _QUEUE.get(action_id)
        if not entry or entry["status"] != "pending":
            return None
        entry["status"] = "approved" if approve else "rejected"
        entry["decided_ts"] = time.time()
        _persist()
    audit.log("approval.decide", id=action_id, approved=approve)
    return entry


def mark_applied(action_id: str) -> None:
    with _LOCK:
        entry = _QUEUE.get(action_id)
        if entry:
            entry["status"] = "applied"
            entry["applied_ts"] = time.time()
            _persist()
    audit.log("approval.applied", id=action_id)


def is_approved(action_id: str) -> bool:
    with _LOCK:
        entry = _QUEUE.get(action_id)
        return bool(entry and entry["status"] in ("approved", "applied"))


def pending() -> list[dict[str, Any]]:
    with _LOCK:
        return [e for e in _QUEUE.values() if e["status"] == "pending"]


def all_actions(limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK:
        items = sorted(_QUEUE.values(), key=lambda e: e["ts"], reverse=True)
    return items[:limit]


def get(action_id: str) -> dict[str, Any] | None:
    with _LOCK:
        return _QUEUE.get(action_id)
