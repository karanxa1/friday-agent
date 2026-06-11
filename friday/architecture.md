# Friday — Architecture

Friday is a self-modifying, self-learning autonomous agent built on **Google ADK**,
**local Claude models** (Anthropic-protocol endpoint), and **MCP**. It ports proven
self-improvement primitives onto a smaller, ADK-native core.

## High-level

```
┌──────────────────────────────────────────────────────────────┐
│ CONTROL PLANE (FastAPI)  — control_plane/                      │
│  registries (agents/tools/mcp) · builder.hot_reload() ·        │
│  approval queue · curator · audit (git + JSONL) · dashboard    │
└───────────────┬───────────────────────────────────────────────┘
        builds/hot-reloads ↓
┌──────────────────────────────────────────────────────────────┐
│ FRIDAY ROOT AGENT (Opus 4.8)  — registry/agents.json          │
│  plan → act → measure → adapt → learn                          │
└──┬──────────┬───────────┬───────────┬──────────┬──────────────┘
   ▼          ▼           ▼           ▼          ▼
 SELF-DEV   SKILLS     DELEGATE    SANDBOX    CAPABILITY + AUTH
 (edit own  (create/   (spawn_     (docker    (create_tool/
  code+git)  edit       subagent,   exec,      create_mcp_server,
             skills)    depth-cap)  isolated)  encrypted vault)
   +MCP tools: callmissed-search · metrics(mock) · yourmemory · vision
   +DOMAIN: social-media manager (Scout/Studio/Publisher/Ads/Analyst)
```

## Components

| Area | Module | What it does |
|---|---|---|
| Model routing | `core/model.py` | `LiteLlm` factory; `claude-opus-4-8` (hard) / `claude-sonnet-4-6` (easy); `classify_difficulty()` picks a tier. |
| Config | `core/config.py` | env-driven settings + `~/.friday` runtime home layout. |
| Audit | `core/audit.py` | structured JSONL + in-memory ring; secret scrubbing. |
| Tool registry | `core/registry.py` | toolsets → callables; generation counter for hot-reload. |
| Builder | `control_plane/builder.py` | builds `LlmAgent`s from the registry; attaches MCP toolsets; `hot_reload()`. |
| Conversation | `core/conversation.py` | `run_once()` — runs an agent to completion, logs tool calls. |
| Skills | `skills/` | procedural memory: create/edit/patch + two-tier list/view; **provenance ContextVar** (agent vs user). |
| Delegation | `delegate/spawn.py` | `spawn_subagent`: constrained child toolsets, depth cap, tier routing, summary-only return. |
| Self-dev | `self_dev/tools.py` | read/write/edit own code, validate, git snapshot/revert, reload — **approval-gated, git-backed**. |
| Sandbox | `sandbox/docker_env.py` | hardened Docker exec: `--network none`, `--cap-drop ALL`, `--no-new-privileges`, secret-scrubbed env. |
| Capability | `capability/tools.py` | agent authors new tools / MCP servers, registers + hot-loads them (gated). |
| Auth | `auth/` | encrypted Fernet vault + credential-request flow (secrets never enter model context). |
| Memory | `memory/store.py` | `MEMORY.md`/`USER.md`, frozen snapshot for prompt-cache stability. |
| Curator | `curator/curator.py` | archive-only skill lifecycle (active→stale→archived); only agent-created, never pinned. |
| Social pack | `domains/social_media/` | Scout → Studio → Publisher(gated) → Analyst → AdManager(gated) loop. |
| MCP servers | `mcp_tools/` | callmissed search (real), mock metrics, vision; `generated/` for agent-authored ones. |
| Approvals | `control_plane/approvals.py` | human-in-the-loop gate; autonomy levels L0/L1/L2. |
| Evals | `evals/harness.py` | success rate / latency / approx cost per run. |
| Reliability | `core/reliability.py` | retry+backoff, wall-clock stall guard. |

## Key design decisions

- **Prompt-cache stability** — system prompt built once per session; dynamic
  state (memory snapshot) injected into the user message, not the system prompt.
- **Provenance ContextVar** — the single bit that lets the curator distinguish
  "skills I made" from "skills the user made"; only the former are auto-managed.
- **Archive-only curator** — the most destructive action is moving a skill dir
  into `skills/.archive/`. Nothing is hard-deleted.
- **Constrained delegation** — a child agent's toolset is a subset of the
  parent's; leaves can't delegate further; a depth cap prevents runaway recursion.
- **Sandbox is the security boundary** — arbitrary code runs in Docker, never
  on the host; the child env is scrubbed of secrets.
- **Everything sensitive is gated + git-backed** — self-edits, new
  tools/MCP/skills, publishing, ad-spend, and new credentials all pass through
  the approval queue; self-edits are git commits and revertable.

## MCP "bring your own tools"

External capability is added by registering an MCP server in `registry/mcp.json`;
the builder attaches it to an agent via ADK's `MCPToolset`. The agent itself can
author a new MCP server at runtime via `create_mcp_server` (gated), which writes
the server into `mcp_tools/generated/` and registers it — extensibility is a
first-class, agent-usable feature.

## Models

The local endpoint speaks the **Anthropic Messages API** (`/v1/messages`).
We route through `LiteLlm(model="anthropic/<id>", api_base, api_key)`. Vision is
supported (the model reads images), powering the `analyze_image` tool.
