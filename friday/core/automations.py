"""Scheduled automations (parity with the reference cron/scheduler.py).

Recurring goals run by the root agent on an interval — "check trends every
morning", "post a weekly recap". Safety posture:
* agent-created jobs are gated through the approval queue;
* every job's goal is injection-screened at creation AND again at run time
  (catches payloads smuggled in later via skills/memory);
* runs are audited with the outcome snippet.

The scheduler is a background asyncio task started by the control plane; it
ticks every 60s and runs due jobs sequentially.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core import audit
from core.config import settings
from core.registry import tool
from core.threat_patterns import scan_or_error

_MIN_INTERVAL_MIN = 5
TICK_SECONDS = 60


def _store_path():
    return settings.home / "automations.json"


def load_jobs() -> list[dict[str, Any]]:
    p = _store_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return []


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    settings.ensure_home()
    _store_path().write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")


def add_job(name: str, goal: str, interval_minutes: int, created_by: str) -> dict[str, Any] | str:
    """Validated insert. Returns the job dict, or an 'error: …' string."""
    name = (name or "").strip()
    goal = (goal or "").strip()
    if not name or not goal:
        return "error: name and goal are required"
    if threat := scan_or_error(goal, f"automation {name!r}"):
        return threat
    interval = max(_MIN_INTERVAL_MIN, int(interval_minutes))
    job = {
        "id": uuid.uuid4().hex[:10],
        "name": name,
        "goal": goal,
        "interval_minutes": interval,
        "enabled": True,
        "created_by": created_by,
        "created": time.time(),
        "last_run": 0.0,
        "last_result": "",
    }
    jobs = load_jobs()
    jobs.append(job)
    save_jobs(jobs)
    audit.log("automation.added", id=job["id"], name=name, interval=interval, by=created_by)
    return job


def remove_job(job_id: str) -> bool:
    jobs = load_jobs()
    kept = [j for j in jobs if j["id"] != job_id]
    if len(kept) == len(jobs):
        return False
    save_jobs(kept)
    audit.log("automation.removed", id=job_id)
    return True


async def tick() -> int:
    """Run every due job once. Returns how many jobs ran."""
    from control_plane import builder
    from core.conversation import run_once

    now = time.time()
    jobs = load_jobs()
    ran = 0
    for job in jobs:
        if not job.get("enabled"):
            continue
        if now - float(job.get("last_run") or 0) < job["interval_minutes"] * 60:
            continue
        # Re-screen at run time (assembled-prompt scanning).
        if scan_or_error(job["goal"], f"automation {job['name']!r} (run-time)"):
            job["enabled"] = False
            job["last_result"] = "disabled: goal flagged by injection screening"
            continue
        job["last_run"] = now
        save_jobs(jobs)  # persist BEFORE the run so crashes don't double-fire
        audit.log("automation.run", id=job["id"], name=job["name"])
        try:
            agent = builder.build_agent("root")
            out = await run_once(agent, job["goal"])
            job["last_result"] = (out or "")[:500]
        except Exception as exc:  # noqa: BLE001 — one bad job must not kill the loop
            job["last_result"] = f"error: {exc}"[:500]
            audit.log("automation.error", id=job["id"], error=str(exc)[:200])
        ran += 1
        save_jobs(jobs)
    return ran


# --- agent-facing tools (creation gated) ------------------------------------


@tool("automations", description="Schedule a recurring goal (gated; runs every N minutes).")
def automation_add(name: str, goal: str, interval_minutes: int = 60) -> str:
    """Stage a recurring automation for user approval.

    Args:
        name: short label, e.g. 'morning-trends'.
        goal: the goal the root agent runs each time.
        interval_minutes: how often to run (minimum 5).
    """
    from control_plane import approvals

    if threat := scan_or_error(goal, f"automation {name!r}"):
        return threat
    entry = approvals.submit(
        "capability",
        summary=f"schedule automation {name!r} every {max(_MIN_INTERVAL_MIN, int(interval_minutes))}m: {goal[:80]}",
        payload={
            "kind": "automation_add",
            "name": name,
            "goal": goal,
            "interval_minutes": int(interval_minutes),
        },
    )
    return (
        f"staged automation {name!r} (request {entry['id']}). After the user approves, "
        f"call automation_apply('{entry['id']}')."
    )


@tool("automations", description="Apply an approved automation request.")
def automation_apply(action_id: str) -> str:
    """Activate a previously-approved automation_add request.

    Args:
        action_id: the approval id returned by automation_add.
    """
    from control_plane import approvals

    if not approvals.is_approved(action_id):
        return f"error: request {action_id!r} not approved yet"
    entry = approvals.get(action_id)
    if not entry or entry["payload"].get("kind") != "automation_add":
        return f"error: {action_id!r} is not an automation request"
    p = entry["payload"]
    job = add_job(p["name"], p["goal"], p["interval_minutes"], created_by="agent")
    if isinstance(job, str):
        return job
    approvals.mark_applied(action_id)
    return f"automation {job['name']!r} active (id {job['id']}, every {job['interval_minutes']}m)."


@tool("automations", description="List scheduled automations and their last results.")
def automation_list() -> str:
    """Show every scheduled automation."""
    jobs = load_jobs()
    if not jobs:
        return "(no automations scheduled)"
    return json.dumps(
        [
            {k: j[k] for k in ("id", "name", "goal", "interval_minutes", "enabled", "last_result")}
            for j in jobs
        ],
        ensure_ascii=False,
    )


@tool("automations", description="Remove a scheduled automation by id.")
def automation_remove(job_id: str) -> str:
    """Delete an automation.

    Args:
        job_id: the automation id (see automation_list).
    """
    return f"removed automation {job_id}" if remove_job(job_id) else f"error: {job_id!r} not found"
