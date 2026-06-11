"""Mock metrics MCP server (stands in for live ad/social analytics APIs).

Exposes ``get_metrics`` over stdio MCP, reading seed data from
``data/seed_metrics.json``. Lets the Analyst close the act->measure->adjust
loop without waiting on real API approvals.

Run standalone:  python -m mcp_tools.metrics_server
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("metrics")

# Allow override (tests / alternate datasets); default to repo seed file.
_SEED = os.environ.get("FRIDAY_METRICS_FILE", "").strip()
_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "seed_metrics.json"


def _load() -> dict:
    path = Path(_SEED) if _SEED else _DEFAULT
    if not path.is_file():
        return {"campaigns": [], "posts": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"campaigns": [], "posts": []}


@mcp.tool()
def get_metrics(scope: str = "all") -> str:
    """Return performance metrics for campaigns and/or posts.

    Args:
        scope: "all" (default), "campaigns", or "posts".

    Returns:
        JSON string with the requested metrics.
    """
    data = _load()
    if scope == "campaigns":
        return json.dumps({"campaigns": data.get("campaigns", [])})
    if scope == "posts":
        return json.dumps({"posts": data.get("posts", [])})
    return json.dumps(data)


if __name__ == "__main__":
    mcp.run()
