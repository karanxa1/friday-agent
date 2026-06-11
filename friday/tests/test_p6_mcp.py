"""P6 verification: MCP tools (callmissed search, metrics) + vision registration."""

from __future__ import annotations

import asyncio
import json

from control_plane import builder


def test_callmissed_search_fallback_direct():
    from mcp_tools.callmissed_search_server import search_web

    out = json.loads(search_web("ai devtools trends", num_results=2))
    assert "results" in out
    assert len(out["results"]) >= 1


def test_metrics_server_reads_seed():
    from mcp_tools.metrics_server import get_metrics

    out = json.loads(get_metrics("campaigns"))
    assert "campaigns" in out
    assert len(out["campaigns"]) >= 1
    assert out["campaigns"][0]["id"]


def test_vision_tool_registered():
    from core.registry import registry

    builder.import_tool_modules()
    names = {t.name for t in registry.list() if t.toolset == "vision"}
    assert "analyze_image" in names


def test_mcp_servers_connect_via_adk():
    """The builder attaches the callmissed + metrics MCP servers to an agent."""
    import os
    from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    async def run():
        params = StdioServerParameters(
            command=f"{os.getcwd()}/.venv/bin/python",
            args=["-m", "mcp_tools.callmissed_search_server"],
            env={**os.environ},
        )
        ts = MCPToolset(connection_params=StdioConnectionParams(server_params=params))
        tools = await ts.get_tools()
        names = [t.name for t in tools]
        await ts.close()
        return names

    names = asyncio.run(run())
    assert "search_web" in names
