"""Capability toolset: Friday writes its own tools and MCP servers.

This is the heart of self-extension (the reference "capability lives at the edges"):

* ``create_tool(name, toolset, code)`` -- writes a new native tool module under
  ``capability/generated/`` (gated), registers it, and hot-loads it so the new
  tool is callable immediately.
* ``create_mcp_server(name, code)`` -- writes a FastMCP stdio server under
  ``mcp_tools/generated/`` and registers it in ``registry/mcp.json`` so the
  builder can attach it to an agent.
* ``list_capabilities()`` -- show generated tools/servers.

All writes go through the approval gate and are git-committed via the self_dev
git helper, so every new capability is reviewable and revertable.
"""

from __future__ import annotations

import json
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool, registry
from control_plane import approvals

_GEN_TOOLS = Path(__file__).resolve().parent / "generated"
_GEN_MCP = Path(__file__).resolve().parent.parent / "mcp_tools" / "generated"

_TOOL_TEMPLATE = '''"""Agent-generated tool module: {name}."""

from core.registry import tool


@tool({toolset!r}, description={description!r})
{code}
'''


def _ensure_pkg(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    init = path / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")


@tool("capability", description="Create a new native tool from a Python function body (gated).")
def create_tool(name: str, toolset: str, function_code: str, description: str = "") -> str:
    """Author a new native tool and hot-load it after approval.

    Args:
        name: module/tool base name (lowercase, identifier-safe).
        toolset: toolset to register the tool under (e.g. 'custom').
        function_code: a full ``def <name>(...) -> str:`` definition (the body
            should return a string). It will be decorated with @tool automatically.
        description: one-line description for the tool.
    """
    if not name.isidentifier():
        return f"error: {name!r} is not a valid identifier"
    entry = approvals.submit(
        "capability",
        summary=f"create_tool {name} in toolset '{toolset}'",
        payload={"kind": "tool", "name": name, "toolset": toolset, "code": function_code, "description": description},
    )
    return f"staged new tool {name!r} (request {entry['id']}). Approve, then call apply_capability('{entry['id']}')."


@tool("capability", description="Create a new FastMCP stdio server from Python code (gated).")
def create_mcp_server(name: str, server_code: str, description: str = "") -> str:
    """Author a new MCP server and register it in the MCP registry after approval.

    Args:
        name: server name (lowercase identifier; becomes the registry key).
        server_code: full Python source for a FastMCP server module that defines
            ``mcp = FastMCP(...)``, decorates tools with ``@mcp.tool()``, and calls
            ``mcp.run()`` under ``if __name__ == '__main__'``.
        description: one-line description.
    """
    if not name.isidentifier():
        return f"error: {name!r} is not a valid identifier"
    entry = approvals.submit(
        "capability",
        summary=f"create_mcp_server {name}",
        payload={"kind": "mcp", "name": name, "code": server_code, "description": description},
    )
    return f"staged new MCP server {name!r} (request {entry['id']}). Approve, then apply_capability('{entry['id']}')."


@tool("capability", description="Apply an approved capability (tool/MCP server): write, register, load.")
def apply_capability(action_id: str) -> str:
    """Apply a previously-approved create_tool/create_mcp_server request.

    Args:
        action_id: the approval id returned by create_tool/create_mcp_server.
    """
    if not approvals.is_approved(action_id):
        return f"error: capability {action_id!r} not approved yet"
    entry = approvals.get(action_id)
    if not entry:
        return f"error: {action_id!r} not found"
    payload = entry["payload"]

    if payload["kind"] == "tool":
        _ensure_pkg(_GEN_TOOLS)
        name = payload["name"]
        module_src = _TOOL_TEMPLATE.format(
            name=name,
            toolset=payload["toolset"],
            description=payload["description"] or name,
            code=payload["code"].strip(),
        )
        path = _GEN_TOOLS / f"{name}.py"
        path.write_text(module_src, encoding="utf-8")
        # Validate syntax.
        import py_compile

        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            path.unlink(missing_ok=True)
            return f"error: generated tool has a syntax error: {exc}"
        # Hot-load via the builder's module list.
        from control_plane.builder import register_tool_module

        register_tool_module(f"capability.generated.{name}")
        approvals.mark_applied(action_id)
        audit.log("capability.tool_created", name=name, toolset=payload["toolset"])
        return f"created + loaded tool {name!r} in toolset '{payload['toolset']}'"

    # MCP server
    _ensure_pkg(_GEN_MCP)
    name = payload["name"]
    path = _GEN_MCP / f"{name}.py"
    path.write_text(payload["code"], encoding="utf-8")
    import py_compile

    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        path.unlink(missing_ok=True)
        return f"error: generated MCP server has a syntax error: {exc}"
    # Register in mcp.json so the builder can attach it.
    reg_path = settings.registry_dir / "mcp.json"
    cfg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.is_file() else {"servers": {}}
    cfg.setdefault("servers", {})[name] = {
        "command": f"{settings.registry_dir.parent}/.venv/bin/python",
        "args": ["-m", f"mcp_tools.generated.{name}"],
        "env": {},
        "description": payload["description"] or f"agent-generated MCP server {name}",
    }
    reg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    approvals.mark_applied(action_id)
    audit.log("capability.mcp_created", name=name)
    return f"created MCP server {name!r}; registered in mcp.json. Add it to an agent's 'mcp' list to use."


@tool("capability", description="List agent-generated tools and MCP servers.")
def list_capabilities() -> str:
    """Show generated tool modules and MCP servers."""
    tools = [p.stem for p in _GEN_TOOLS.glob("*.py") if p.stem != "__init__"] if _GEN_TOOLS.exists() else []
    servers = [p.stem for p in _GEN_MCP.glob("*.py") if p.stem != "__init__"] if _GEN_MCP.exists() else []
    return json.dumps({"generated_tools": tools, "generated_mcp_servers": servers})
