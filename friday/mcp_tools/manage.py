"""MCP management toolset: the agent extends itself with existing MCP servers.

Complements :mod:`capability.tools` (which *authors* new servers from code):
here the agent registers pre-built servers (npx/uvx/binary), attaches them to
itself, and drives the auth flow when a server needs credentials.

Everything that changes what the agent can do is gated through the approval
queue; credentials go through the encrypted vault and never enter the model's
context.
"""

from __future__ import annotations

import json
import shlex
from typing import Any

from core import audit
from core.config import settings
from core.registry import tool
from control_plane import approvals


def _load_mcp() -> dict[str, Any]:
    p = settings.registry_dir / "mcp.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"servers": {}}


def _save_mcp(cfg: dict[str, Any]) -> None:
    (settings.registry_dir / "mcp.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


@tool("mcp", description="List registered MCP servers with attachment and auth status.")
def list_mcp_servers() -> str:
    """Show every registered MCP server, who uses it, and whether it is authenticated."""
    from control_plane import builder

    cfg = _load_mcp().get("servers", {})
    agents = builder.load_registry("agents.json").get("agents", {})
    used_by: dict[str, list[str]] = {}
    for aname, spec in agents.items():
        for s in spec.get("mcp", []):
            used_by.setdefault(s, []).append(aname)
    out = []
    for name, spec in cfg.items():
        status = builder.mcp_auth_status(spec)
        out.append(
            {
                "name": name,
                "description": spec.get("description", ""),
                "attached_to": used_by.get(name, []),
                "authenticated": status["authenticated"],
                "missing_credentials": status["missing"],
            }
        )
    return json.dumps({"servers": out}, ensure_ascii=False)


@tool("mcp", description="Register an existing MCP server (npx/uvx/binary) for later attach (gated).")
def add_mcp_server(
    name: str, command_line: str, description: str = "", requires: str = ""
) -> str:
    """Stage the registration of a pre-built MCP server.

    Args:
        name: registry key (identifier-safe, e.g. 'github').
        command_line: full launch command, e.g. 'npx -y @modelcontextprotocol/server-github'.
        description: one line on what the server provides.
        requires: comma-separated env keys the server needs (e.g. 'GITHUB_TOKEN').
            Missing keys trigger the credential/auth flow before the server is used.
    """
    if not name.replace("_", "").replace("-", "").isalnum():
        return f"error: {name!r} is not a valid server name"
    parts = shlex.split(command_line.strip())
    if not parts:
        return "error: command_line is empty"
    from core.osv_check import malware_advisories

    bad = malware_advisories(parts[0], parts[1:])
    if bad:
        return (
            f"error: package blocked — known malware advisories {bad} (OSV.dev). "
            f"Do not register this server."
        )
    req_keys = [k.strip() for k in requires.split(",") if k.strip()]
    entry = approvals.submit(
        "capability",
        summary=f"register MCP server {name}: {command_line[:120]}",
        payload={
            "kind": "mcp_register",
            "name": name,
            "command": parts[0],
            "args": parts[1:],
            "description": description,
            "requires": req_keys,
        },
    )
    return (
        f"staged MCP server {name!r} (request {entry['id']}). After the user approves, "
        f"call apply_mcp_change('{entry['id']}')."
    )


@tool("mcp", description="Attach a registered MCP server to an agent so its tools become usable (gated).")
def attach_mcp_server(server: str, agent: str = "root") -> str:
    """Stage attaching a server to an agent (takes effect after approval + apply).

    Args:
        server: registered server name (see list_mcp_servers).
        agent: agent to extend (default 'root').
    """
    if server not in _load_mcp().get("servers", {}):
        return f"error: server {server!r} is not registered (use add_mcp_server first)"
    entry = approvals.submit(
        "capability",
        summary=f"attach MCP server {server} to agent {agent}",
        payload={"kind": "mcp_attach", "server": server, "agent": agent},
    )
    return (
        f"staged attach of {server!r} to {agent!r} (request {entry['id']}). After the user "
        f"approves, call apply_mcp_change('{entry['id']}')."
    )


@tool("mcp", description="Apply an approved MCP registration/attachment.")
def apply_mcp_change(action_id: str) -> str:
    """Apply a previously-approved add_mcp_server / attach_mcp_server request.

    Args:
        action_id: the approval id returned when the change was staged.
    """
    from control_plane import builder

    if not approvals.is_approved(action_id):
        return f"error: request {action_id!r} not approved yet — ask the user to approve it"
    entry = approvals.get(action_id)
    if not entry:
        return f"error: request {action_id!r} not found"
    payload = entry["payload"]
    kind = payload.get("kind")

    if kind == "mcp_register":
        cfg = _load_mcp()
        cfg.setdefault("servers", {})[payload["name"]] = {
            "command": payload["command"],
            "args": payload["args"],
            "env": {},
            "description": payload["description"],
            "requires": payload["requires"],
        }
        _save_mcp(cfg)
        approvals.mark_applied(action_id)
        audit.log("mcp.registered_by_agent", name=payload["name"])
        status = builder.mcp_auth_status(cfg["servers"][payload["name"]])
        note = (
            "" if status["authenticated"]
            else f" NOTE: missing credentials {status['missing']} — call request_mcp_auth('{payload['name']}')."
        )
        return f"registered MCP server {payload['name']!r}.{note}"

    if kind == "mcp_attach":
        apath = settings.registry_dir / "agents.json"
        agents = builder.load_registry("agents.json")
        spec = agents.get("agents", {}).get(payload["agent"])
        if spec is None:
            return f"error: agent {payload['agent']!r} not found"
        mcp_list = spec.setdefault("mcp", [])
        if payload["server"] not in mcp_list:
            mcp_list.append(payload["server"])
        apath.write_text(json.dumps(agents, indent=2), encoding="utf-8")
        builder.hot_reload()
        approvals.mark_applied(action_id)
        audit.log("mcp.attached_by_agent", server=payload["server"], agent=payload["agent"])
        return (
            f"attached {payload['server']!r} to {payload['agent']!r}. Its tools are available "
            f"in new conversations."
        )

    return f"error: {action_id!r} is not an MCP change request"


@tool("mcp", description="Ask the user to authenticate an MCP server that is missing credentials.")
def request_mcp_auth(server: str) -> str:
    """File credential requests for every key a server still needs.

    Args:
        server: registered server name.
    """
    from auth.tools import request_credential
    from control_plane import builder

    spec = _load_mcp().get("servers", {}).get(server)
    if not spec:
        return f"error: server {server!r} is not registered"
    status = builder.mcp_auth_status(spec)
    if status["authenticated"]:
        return f"{server!r} is fully authenticated — nothing to do."
    notes = [
        request_credential(
            service=f"MCP server {server}",
            key_name=key,
            instructions=f"Required by the {server} MCP server ({spec.get('description', '')}).",
        )
        for key in status["missing"]
    ]
    return (
        f"requested {len(notes)} credential(s) for {server!r}: {', '.join(status['missing'])}. "
        f"The user can supply them in the Approvals panel or the MCP page; they are stored "
        f"encrypted and never shown to me.\n" + "\n".join(notes)
    )
