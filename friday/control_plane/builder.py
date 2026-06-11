"""Agent builder + hot-reload (inspired by Friday' registry/gateway rebuild).

Reads the JSON registries under ``registry/`` and constructs ADK ``LlmAgent``
instances. Native Python tools come from :mod:`core.registry`; MCP tools are
attached via ADK's ``MCPToolset``.

``hot_reload`` lets the running process pick up edited tool modules, new
registry entries, and new MCP servers without a restart -- the mechanism that
makes Friday self-modifying.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent

from core import audit
from core.config import settings
from core.model import make_llm
from core.registry import registry

# Tool modules that should be imported so they self-register into the registry.
# Hot-reload re-imports these. New modules can be appended at runtime.
_TOOL_MODULES: list[str] = [
    "core.builtin_tools",
    "skills.manager",
    "delegate.spawn",
    "self_dev.tools",
    "mcp_tools.vision",
    "domains.social_media.tools",
    "memory.store",
    "auth.tools",
    "capability.tools",
    "sandbox.docker_env",
    "friday_tools.files",
    "friday_tools.web",
    "friday_tools.research",
    "friday_tools.media",
    "friday_tools.browser",
    "friday_tools.computer",
    "friday_tools.voice",
    "core.automations",
    "friday_tools.todo",
    "friday_tools.recall",
    "friday_tools.system",
    "friday_tools.artifacts",
    "mcp_tools.manage",
]

# Cache of live MCPToolset instances so we can close them on reload.
_mcp_toolsets: list[Any] = []

# Tool names reserved by provider server-side built-ins. If a native or MCP
# tool uses one of these, the Anthropic-protocol endpoint silently DISABLES
# extended thinking whenever that tool is in the request (verified: a tool
# named ``web_search`` drops thinking_deltas from 17 to 0). Keep custom tools
# off these names. ``_check_reserved_names`` warns at build time.
RESERVED_TOOL_NAMES: frozenset[str] = frozenset(
    {"web_search", "web_fetch", "bash", "text_editor", "computer", "code_execution", "str_replace_editor"}
)


def _check_reserved_names() -> None:
    """Warn if any registered native tool collides with a provider built-in."""
    for entry in registry.list():
        if entry.name in RESERVED_TOOL_NAMES:
            audit.log(
                "builder.reserved_tool_name",
                tool=entry.name,
                toolset=entry.toolset,
                warning="collides with a provider built-in; may disable thinking",
            )


def _registry_path(name: str) -> Path:
    return settings.registry_dir / name


def load_registry(name: str) -> dict[str, Any]:
    path = _registry_path(name)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        audit.log("builder.registry_error", file=name, error=str(exc))
        return {}


def import_tool_modules(reload: bool = False) -> None:
    """Import (or re-import) the tool modules so they register their tools."""
    for mod_name in list(_TOOL_MODULES):
        try:
            mod = importlib.import_module(mod_name)
            if reload:
                importlib.reload(mod)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            audit.log("builder.tool_import_error", module=mod_name, error=str(exc))


def register_tool_module(dotted_path: str) -> None:
    """Add a tool module to the import list (used by the capability toolset)."""
    if dotted_path not in _TOOL_MODULES:
        _TOOL_MODULES.append(dotted_path)
        import_tool_modules()
        audit.log("builder.tool_module_added", module=dotted_path)


def mcp_env_for(spec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Resolve the env an MCP server subprocess gets, honoring its auth needs.

    Precedence: process env < per-server ``env`` overrides < vault credentials
    for declared ``requires`` keys. Returns (env, missing_required_keys).
    """
    import os as _os

    from auth import vault

    env: dict[str, str] = {**_os.environ, **(spec.get("env") or {})}
    missing: list[str] = []
    for key in spec.get("requires") or []:
        if env.get(key):
            continue
        val = vault.get_credential(key)
        if val:
            env[key] = val
        else:
            missing.append(key)
    return env, missing


def mcp_auth_status(spec: dict[str, Any]) -> dict[str, Any]:
    """Auth summary for one server spec: which keys it needs, which are missing."""
    _, missing = mcp_env_for(spec)
    required = list(spec.get("requires") or [])
    return {"requires": required, "missing": missing, "authenticated": not missing}


def _build_mcp_toolsets(server_names: list[str]) -> list[Any]:
    """Construct MCPToolset instances for the named servers in mcp.json."""
    if not server_names:
        return []
    try:
        from google.adk.tools.mcp_tool import (
            MCPToolset,
            SseConnectionParams,
            StdioConnectionParams,
            StreamableHTTPConnectionParams,
        )
        from mcp import StdioServerParameters
    except Exception as exc:  # noqa: BLE001
        audit.log("builder.mcp_unavailable", error=str(exc))
        return []

    cfg = load_registry("mcp.json").get("servers", {})
    toolsets: list[Any] = []
    for name in server_names:
        spec = cfg.get(name)
        if not spec:
            audit.log("builder.mcp_missing", server=name)
            continue
        merged_env, missing = mcp_env_for(spec)
        if missing:
            # Server declares required credentials we don't have anywhere
            # (env, per-server overrides, vault). Don't attach a broken
            # server — surface it so the UI/agent can ask the user.
            audit.log("builder.mcp_needs_auth", server=name, missing=",".join(missing))
            continue
        try:
            conn = _mcp_connection_params(
                spec,
                merged_env,
                StdioServerParameters=StdioServerParameters,
                StdioConnectionParams=StdioConnectionParams,
                SseConnectionParams=SseConnectionParams,
                StreamableHTTPConnectionParams=StreamableHTTPConnectionParams,
            )
            ts = MCPToolset(connection_params=conn)
            toolsets.append(ts)
            _mcp_toolsets.append(ts)
            audit.log("builder.mcp_attached", server=name, transport=_mcp_transport(spec))
        except Exception as exc:  # noqa: BLE001
            audit.log("builder.mcp_attach_error", server=name, error=str(exc))
    return toolsets


def _mcp_transport(spec: dict[str, Any]) -> str:
    """Resolve a server's transport: explicit ``transport``, else inferred from
    the presence of a ``url`` (remote) vs ``command`` (local stdio)."""
    t = str(spec.get("transport") or "").lower().replace("-", "_")
    if t:
        return "streamable_http" if t in ("http", "streamable_http", "streamablehttp") else t
    return "streamable_http" if spec.get("url") else "stdio"


def _subst_env(value: str, env: dict[str, str]) -> str:
    """Expand ``${VAR}`` references in a header/value from the resolved env so
    auth tokens (e.g. ``Authorization: Bearer ${HF_TOKEN}``) stay out of the
    committed registry and come from the vault/process env at attach time."""
    import re as _re

    return _re.sub(r"\$\{(\w+)\}", lambda m: env.get(m.group(1), ""), value)


def _mcp_connection_params(
    spec: dict[str, Any],
    merged_env: dict[str, str],
    *,
    StdioServerParameters: Any,
    StdioConnectionParams: Any,
    SseConnectionParams: Any,
    StreamableHTTPConnectionParams: Any,
) -> Any:
    """Build the right ADK connection params for a server spec.

    Local servers (``command``) use stdio. Remote/interactive servers (Hugging
    Face, Gradio Spaces, MCP-UI apps) declare a ``url`` and optional
    ``transport`` ("sse" | "http") plus ``headers`` with ``${ENV}`` placeholders
    resolved from the vault/env. This is what lets the agent attach the
    interactive MCP servers whose tools return UIResources.
    """
    transport = _mcp_transport(spec)
    if transport in ("sse", "streamable_http"):
        url = str(spec["url"])
        headers = {k: _subst_env(str(v), merged_env) for k, v in (spec.get("headers") or {}).items()}
        if transport == "sse":
            return SseConnectionParams(url=url, headers=headers or None)
        return StreamableHTTPConnectionParams(url=url, headers=headers or None)
    params = StdioServerParameters(
        command=spec["command"],
        args=spec.get("args", []),
        env=merged_env,
    )
    return StdioConnectionParams(server_params=params)


def build_agent(agent_name: str = "root") -> LlmAgent:
    """Build an ADK ``LlmAgent`` from the registry definition."""
    import_tool_modules()
    _check_reserved_names()
    agents = load_registry("agents.json").get("agents", {})
    spec = agents.get(agent_name)
    if spec is None:
        raise KeyError(f"agent '{agent_name}' not found in registry/agents.json")

    tier = spec.get("tier", "easy")
    toolsets = spec.get("toolsets", [])
    mcp_servers = spec.get("mcp", [])

    native_tools = registry.resolve(toolsets)
    mcp_tools = _build_mcp_toolsets(mcp_servers)
    tools = [*native_tools, *mcp_tools]

    instruction = _build_instruction(agent_name, spec)

    agent = LlmAgent(
        name=agent_name,
        model=make_llm(tier),
        description=spec.get("description", ""),
        instruction=instruction,
        tools=tools,
    )
    audit.log(
        "builder.agent_built",
        agent=agent_name,
        tier=tier,
        native_tools=len(native_tools),
        mcp_tools=len(mcp_tools),
        registry_gen=registry.generation,
    )
    return agent


def _build_instruction(agent_name: str, spec: dict[str, Any]) -> str:
    """Compose a stable system instruction.

    Per the Friday prompt-cache pattern, this is built deterministically from
    the registry so it stays byte-stable across turns within a session. The
    base prompt is the Cursor-derived system prompt (core.prompt); any
    per-agent ``instruction`` in the registry is appended as a suffix.
    """
    from core.prompt import build_system_prompt

    extra = spec.get("instruction", "")
    toolsets = spec.get("toolsets", [])
    return build_system_prompt(toolsets=toolsets, extra=extra)


def hot_reload() -> dict[str, Any]:
    """Re-import tool modules and close stale MCP toolsets.

    Returns a small status dict for the UI/audit. Callers rebuild agents
    afterwards via :func:`build_agent`.
    """
    # Close any open MCP toolsets so re-attach is clean.
    closed = 0
    for ts in list(_mcp_toolsets):
        close = getattr(ts, "close", None)
        if callable(close):
            try:
                result = close()
                # MCPToolset.close may be async; ignore awaitable here (best effort).
                if hasattr(result, "__await__"):
                    import asyncio

                    try:
                        asyncio.get_event_loop().run_until_complete(result)
                    except RuntimeError:
                        pass
                closed += 1
            except Exception:  # noqa: BLE001
                pass
    _mcp_toolsets.clear()

    import_tool_modules(reload=True)
    status = {
        "reloaded_modules": list(_TOOL_MODULES),
        "closed_mcp": closed,
        "registry_gen": registry.generation,
    }
    audit.log("builder.hot_reload", **status)
    return status
