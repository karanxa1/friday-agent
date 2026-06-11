"""Structured audit logging for Friday.

Every meaningful step (agent start/stop, tool call, approval decision,
self-edit, spawn) is appended as a JSON line to ``~/.friday/logs/audit.jsonl``
and mirrored to an in-memory ring buffer the UI can poll.

Audit is intentionally dependency-light and safe to call from anywhere.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from typing import Any

from core.config import settings

_LOCK = threading.Lock()
_RING: deque[dict[str, Any]] = deque(maxlen=2000)

# Patterns we never want to write to the log verbatim.
_SECRET_HINTS = ("api_key", "apikey", "password", "secret", "token", "authorization", "bearer")


def _scrub(value: Any) -> Any:
    """Recursively redact obvious secret-bearing keys."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if any(h in str(k).lower() for h in _SECRET_HINTS):
                out[k] = "<redacted>"
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and value.startswith(("sk-", "cm_", "Bearer ")):
        return "<redacted>"
    return value


def log(event: str, **fields: Any) -> dict[str, Any]:
    """Append an audit event. Returns the recorded entry."""
    scrubbed = _scrub(fields)
    # Callers often pass id=<entity> (approval, todo, …). Never let that
    # clobber the per-event id the UI uses as a React list key.
    if "id" in scrubbed:
        scrubbed["ref_id"] = scrubbed.pop("id")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "event": event,
        **scrubbed,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        _RING.append(entry)
        try:
            settings.ensure_home()
            with (settings.logs_dir / "audit.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            # Never let logging crash the agent.
            pass
    return entry


def recent(limit: int = 100, event_prefix: str | None = None) -> list[dict[str, Any]]:
    """Return the most recent audit entries (newest last)."""
    with _LOCK:
        items = list(_RING)
    if event_prefix:
        items = [e for e in items if str(e.get("event", "")).startswith(event_prefix)]
    return items[-limit:]
