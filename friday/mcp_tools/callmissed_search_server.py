"""CallMissed web-search MCP server (the real "bring your own tools" integration).

Exposes a single ``web_search`` tool over stdio MCP, backed by the CallMissed
Search API.

Provider integration (per callmissed AGENTS.md rule -- cite the upstream doc):
  Endpoint : POST {CALLMISSED_BASE_URL}/v1/search
  Auth     : Authorization: Bearer <CALLMISSED_API_KEY>   (key prefix cm_)
  Request  : {"query": str, "mode": "auto|shorter|detailed", "num_results": int}
  Response : {"results": [{"title","url","snippet","source","published_date","score"}],
              "answer", "credits_used", ...}
  Source   : reference -> callmissed backend/app/api/v1/search.py (router POST /search,
             mounted at /v1) + backend/app/api/v1/docs_export.py curl example.

If CALLMISSED_API_KEY is unset, the tool returns canned fallback trends so the
agent loop runs end-to-end without the key (it clearly labels them as fallback).

Run standalone:  python -m mcp_tools.callmissed_search_server
"""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

_BASE = os.environ.get("CALLMISSED_BASE_URL", "https://api.callmissed.com").rstrip("/")
_KEY = os.environ.get("CALLMISSED_API_KEY", "").strip()

mcp = FastMCP("callmissed-search")


def _fallback(query: str, num_results: int) -> str:
    items = [
        {
            "title": f"[fallback] Trending discussion about {query}",
            "url": "https://example.com/fallback-1",
            "snippet": f"Canned fallback result for {query!r} (CALLMISSED_API_KEY not set).",
            "source": "fallback",
            "published_date": None,
            "score": 0.0,
        },
        {
            "title": f"[fallback] {query}: what people are saying",
            "url": "https://example.com/fallback-2",
            "snippet": "Set CALLMISSED_API_KEY in the environment to get live results.",
            "source": "fallback",
            "published_date": None,
            "score": 0.0,
        },
    ][:num_results]
    return json.dumps({"query": query, "provider": "fallback", "results": items, "fallback": True})


@mcp.tool()
def search_web(query: str, mode: str = "auto", num_results: int = 8) -> str:
    """Search the public web for trends, topics, news, and competitor activity.

    Note: this tool is intentionally named ``search_web`` (not ``web_search``)
    because ``web_search`` collides with Anthropic's server-side built-in tool
    name, which silently disables extended thinking when present in the tool
    list. Keep this name distinct from any provider built-in.

    Args:
        query: the search query (1-2000 chars).
        mode: "auto" (default), "shorter" (Google SERP), or "detailed" (neural).
        num_results: number of results to return (1-50).

    Returns:
        JSON string with a "results" list of {title, url, snippet, source,
        published_date, score} plus provider metadata.
    """
    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "query is required"})
    num_results = max(1, min(int(num_results or 8), 50))

    if not _KEY:
        return _fallback(query, num_results)

    try:
        resp = httpx.post(
            f"{_BASE}/v1/search",
            headers={
                "Authorization": f"Bearer {_KEY}",
                "Content-Type": "application/json",
            },
            json={"query": query, "mode": mode, "num_results": num_results},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        return json.dumps({"error": f"request failed: {exc}", "query": query})

    if resp.status_code != 200:
        return json.dumps(
            {"error": f"callmissed returned {resp.status_code}", "body": resp.text[:500], "query": query}
        )
    return resp.text


if __name__ == "__main__":
    mcp.run()
