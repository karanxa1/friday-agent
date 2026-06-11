"""Social-media domain pack: the flagship "company social media manager".

Five specialist agents wired into one autonomous loop:

    Trend Scout  -> finds trends via the callmissed search_web MCP tool
    Content Studio -> turns trends into on-brand, platform-specific drafts
    Publisher    -> queues posts (gated; sandbox)
    Analyst      -> reads metrics, recommends pause/scale/reallocate
    Ad Manager   -> drafts/adjusts campaigns (gated; sandbox)

The Orchestrator runs them in sequence and synthesizes the result:
    trend -> content -> (gated) publish -> measure -> adjust

Each agent is built from the registry/model factory so it can also spawn
sub-agents and pick its own tier.
"""

from __future__ import annotations

import json
from pathlib import Path

from google.adk.agents import LlmAgent

from core import audit
from core.model import make_llm
from core.registry import registry

_BRAND_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data" / "brand_profile.sample.json"


def load_brand(path: str | None = None) -> dict:
    p = Path(path) if path else _BRAND_DEFAULT
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"brand": "Unknown", "voice": "neutral", "platforms": {}}


def _mcp_tools(server_names: list[str]):
    """Build MCPToolset instances for the given servers (lazy import)."""
    from control_plane.builder import _build_mcp_toolsets

    return _build_mcp_toolsets(server_names)


def build_trend_scout() -> LlmAgent:
    tools = [*registry.resolve(["core", "delegate"]), *_mcp_tools(["callmissed_search"])]
    return LlmAgent(
        name="trend_scout",
        model=make_llm("easy"),
        description="Finds trending topics, hashtags, and competitor activity for a niche.",
        instruction=(
            "You are Trend Scout. Use the search_web tool to find current trends, "
            "hashtags, and competitor activity for the given niche. Return a RANKED "
            "list of 3-5 trends, each with a one-line rationale and a relevance score "
            "0-1. Be concrete. Output as a short markdown list."
        ),
        tools=tools,
    )


def build_content_studio(brand: dict) -> LlmAgent:
    brand_json = json.dumps(brand, ensure_ascii=False)
    return LlmAgent(
        name="content_studio",
        model=make_llm("easy"),
        description="Turns trends into on-brand, platform-specific content drafts.",
        instruction=(
            "You are Content Studio. Given trends and this brand profile, write "
            "platform-specific drafts for X, LinkedIn, and Instagram. Respect each "
            "platform's max_chars and style, and the brand voice/do/dont. For "
            "Instagram include a short image/video concept brief. Stay on-brand; no "
            "hype words.\n\nBRAND PROFILE:\n" + brand_json
        ),
        tools=registry.resolve(["core", "delegate"]),
    )


def build_publisher() -> LlmAgent:
    return LlmAgent(
        name="publisher",
        model=make_llm("easy"),
        description="Queues posts for human approval before publishing (sandbox).",
        instruction=(
            "You are Publisher. For each provided draft, call queue_post(platform, "
            "text, media_brief). NEVER claim a post is live until confirm_publish "
            "succeeds after human approval. Report the approval ids you created."
        ),
        tools=registry.resolve(["core", "publisher"]),
    )


def build_analyst() -> LlmAgent:
    tools = [*registry.resolve(["core", "delegate"]), *_mcp_tools(["metrics"])]
    return LlmAgent(
        name="analyst",
        model=make_llm("hard"),  # decisions over data -> stronger tier
        description="Analyzes performance metrics and recommends pause/scale/reallocate.",
        instruction=(
            "You are Analyst. Call get_metrics to fetch campaign + post performance. "
            "Identify winners and losers using CTR, CPA, and engagement rate. "
            "Recommend concrete actions: which campaigns to PAUSE (losers), SCALE "
            "(winners, with a suggested new daily budget), and how to REALLOCATE "
            "budget. Output a short, decisive action list with reasons and numbers."
        ),
        tools=tools,
    )


def build_ad_manager() -> LlmAgent:
    return LlmAgent(
        name="ad_manager",
        model=make_llm("easy"),
        description="Drafts and adjusts ad campaigns/budgets (gated; sandbox).",
        instruction=(
            "You are Ad Manager. Translate the Analyst's recommendations into "
            "concrete actions using draft_campaign and adjust_budget. ALL spend "
            "changes require approval; never claim a change is applied until "
            "confirm_campaign succeeds. Report the approval ids you created."
        ),
        tools=registry.resolve(["core", "ads"]),
    )
