"""Sandbox publisher + ad-manager tools (gated; no real money, no real accounts).

These stand in for live social/ads APIs. Posts and budget changes are *queued*
to a local SQLite-ish JSON store and routed through the human-approval gate --
matching the "prepare & queue is a feature (safety)" design.

* ``queue_post``      -- stage a social post for approval, then store on approve
* ``list_queue``      -- show queued/published posts
* ``draft_campaign``  -- stage a new ad campaign (approval-gated)
* ``adjust_budget``   -- stage a budget change (approval-gated)

Nothing here contacts a real network. The Publisher could later drive Playwright
against a real test account behind the same gate.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool
from control_plane import approvals

_LOCK = threading.RLock()


def _store_path() -> Path:
    settings.ensure_home()
    return settings.home / "social_store.json"


def _load() -> dict:
    p = _store_path()
    if not p.is_file():
        return {"posts": [], "campaigns": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"posts": [], "campaigns": []}


def _save(data: dict) -> None:
    p = _store_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# --- publisher --------------------------------------------------------------


@tool("publisher", description="Queue a social post for human approval before publishing.")
def queue_post(platform: str, text: str, media_brief: str = "", image_path: str = "") -> str:
    """Stage a social media post (sandbox). Requires approval before it 'publishes'.

    Args:
        platform: "x", "linkedin", or "instagram".
        text: the post caption/body.
        media_brief: optional concept brief for an image/video.
        image_path: optional path to an image to attach. Use generate_image
            first (it self-checks with vision); only attach images whose
            verdict was PASS.

    Returns:
        An approval id; the post is stored only after approval + confirm_publish.
    """
    entry = approvals.submit(
        "publish",
        summary=f"publish to {platform}: {text[:80]}" + (" [+image]" if image_path else ""),
        payload={
            "platform": platform,
            "text": text,
            "media_brief": media_brief,
            "image_path": image_path,
        },
    )
    return (
        f"queued post {entry['id']} for {platform} (status={entry['status']}). "
        f"Approve it, then call confirm_publish('{entry['id']}')."
    )


@tool("publisher", description="Publish a previously-approved queued post (sandbox store).")
def confirm_publish(action_id: str) -> str:
    """Finalize an approved post into the sandbox store.

    Args:
        action_id: the approval id from queue_post.
    """
    if not approvals.is_approved(action_id):
        return f"error: post {action_id!r} not approved yet"
    entry = approvals.get(action_id)
    if not entry:
        return f"error: {action_id!r} not found"
    with _LOCK:
        data = _load()
        post = {
            "id": f"post_{uuid.uuid4().hex[:8]}",
            "approval_id": action_id,
            **entry["payload"],
            "published_at": time.time(),
            "status": "published",
        }
        data["posts"].append(post)
        _save(data)
    approvals.mark_applied(action_id)
    audit.log("publisher.published", post_id=post["id"], platform=post["platform"])
    return f"published {post['id']} to {post['platform']} (sandbox)"


@tool("publisher", description="List queued and published posts from the sandbox store.")
def list_queue() -> str:
    """Return all sandbox posts (queued + published)."""
    data = _load()
    return json.dumps({"posts": data.get("posts", [])})


# --- ad manager -------------------------------------------------------------


@tool("ads", description="Draft a new ad campaign (sandbox; requires approval).")
def draft_campaign(platform: str, name: str, daily_budget: float, objective: str = "awareness") -> str:
    """Stage a new ad campaign draft. Requires approval (spend-sensitive).

    Args:
        platform: ad platform.
        name: campaign name.
        daily_budget: proposed daily budget (no real money is spent).
        objective: campaign objective.
    """
    entry = approvals.submit(
        "ad_spend",
        summary=f"new campaign '{name}' on {platform} @ ${daily_budget}/day",
        payload={
            "op": "create",
            "platform": platform,
            "name": name,
            "daily_budget": float(daily_budget),
            "objective": objective,
        },
    )
    return f"drafted campaign {entry['id']} (status={entry['status']}). Approve, then confirm_campaign."


@tool("ads", description="Stage an ad budget change for an existing campaign (requires approval).")
def adjust_budget(campaign_id: str, new_daily_budget: float, reason: str = "") -> str:
    """Stage a budget change (spend-sensitive; approval-gated).

    Args:
        campaign_id: target campaign id.
        new_daily_budget: the proposed new daily budget.
        reason: why (e.g. 'scaling winner', 'pausing loser').
    """
    entry = approvals.submit(
        "ad_spend",
        summary=f"set {campaign_id} budget -> ${new_daily_budget}/day ({reason})",
        payload={"op": "adjust", "campaign_id": campaign_id, "new_daily_budget": float(new_daily_budget), "reason": reason},
    )
    return f"staged budget change {entry['id']} (status={entry['status']}). Approve, then confirm_campaign."


@tool("ads", description="Apply an approved campaign create/adjust into the sandbox store.")
def confirm_campaign(action_id: str) -> str:
    """Finalize an approved campaign draft/adjustment into the sandbox store.

    Args:
        action_id: the approval id from draft_campaign/adjust_budget.
    """
    if not approvals.is_approved(action_id):
        return f"error: action {action_id!r} not approved yet"
    entry = approvals.get(action_id)
    if not entry:
        return f"error: {action_id!r} not found"
    payload = entry["payload"]
    with _LOCK:
        data = _load()
        if payload["op"] == "create":
            camp = {
                "id": f"camp_{uuid.uuid4().hex[:8]}",
                "approval_id": action_id,
                "platform": payload["platform"],
                "name": payload["name"],
                "daily_budget": payload["daily_budget"],
                "objective": payload["objective"],
                "status": "active",
            }
            data["campaigns"].append(camp)
            result = f"created campaign {camp['id']} (sandbox)"
        else:  # adjust
            cid = payload["campaign_id"]
            found = next((c for c in data["campaigns"] if c["id"] == cid), None)
            if not found:
                # Allow adjusting seed-metric campaigns by recording an override.
                found = {"id": cid, "status": "active"}
                data["campaigns"].append(found)
            found["daily_budget"] = payload["new_daily_budget"]
            result = f"set {cid} budget -> ${payload['new_daily_budget']}/day (sandbox)"
        _save(data)
    approvals.mark_applied(action_id)
    audit.log("ads.confirmed", action=action_id, op=payload["op"])
    return result


@tool("ads", description="List sandbox ad campaigns.")
def list_campaigns() -> str:
    """Return all sandbox ad campaigns."""
    return json.dumps({"campaigns": _load().get("campaigns", [])})
