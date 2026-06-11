"""The autonomous social-media loop: trend -> content -> publish -> measure -> adjust.

Each stage runs a specialist agent via the shared ``run_once`` helper and feeds
its output into the next. Publish + ad-spend stages produce *queued* (gated)
actions; the loop reports the pending-approval ids rather than acting on money.

This is the closed act->measure->adjust loop, runnable from a single goal.
"""

from __future__ import annotations

from typing import Any

from core import audit
from core.conversation import run_once
from control_plane import approvals
from control_plane.builder import import_tool_modules
from domains.social_media import agents as A


async def run_social_loop(goal: str, niche: str, brand_path: str | None = None) -> dict[str, Any]:
    """Run the full social-media manager loop for a high-level goal.

    Args:
        goal: e.g. "grow launch awareness this week".
        niche: the topic area for trend scouting, e.g. "developer tools".
        brand_path: optional path to a brand profile JSON.

    Returns:
        A dict with each stage's output + the pending-approval queue.
    """
    import_tool_modules()  # ensure publisher/ads/etc registered
    brand = A.load_brand(brand_path)
    audit.log("social_loop.start", goal=goal, niche=niche, brand=brand.get("brand"))

    # 1. Trend Scout
    scout = A.build_trend_scout()
    trends = await run_once(scout, f"Goal: {goal}\nNiche: {niche}\nFind and rank current trends.")

    # 2. Content Studio
    studio = A.build_content_studio(brand)
    content = await run_once(
        studio,
        f"Goal: {goal}\nHere are the ranked trends:\n{trends}\n\n"
        "Write X, LinkedIn, and Instagram drafts based on the top trends.",
    )

    # 3. Publisher (gated)
    publisher = A.build_publisher()
    publish = await run_once(
        publisher,
        f"Queue these drafts for approval (do not publish without approval):\n{content}",
    )

    # 4. Analyst (measure)
    analyst = A.build_analyst()
    analysis = await run_once(
        analyst,
        f"Goal: {goal}\nAnalyze current campaign + post performance and recommend "
        "pause/scale/reallocate actions.",
    )

    # 5. Ad Manager (adjust, gated)
    ads = A.build_ad_manager()
    adjustments = await run_once(
        ads,
        f"Based on these recommendations, draft/adjust campaigns (all gated):\n{analysis}",
    )

    pending = approvals.pending()
    result = {
        "goal": goal,
        "niche": niche,
        "brand": brand.get("brand"),
        "trends": trends,
        "content": content,
        "publish": publish,
        "analysis": analysis,
        "adjustments": adjustments,
        "pending_approvals": pending,
    }
    audit.log("social_loop.done", goal=goal, pending=len(pending))
    return result
