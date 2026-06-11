# Friday (hack-agent) — System Architecture

Friday is a **self-modifying autonomous agent** with a Cursor-style control plane: a Next.js chat UI, a FastAPI backend, Google ADK agent runtime, MCP tool servers, and human approval gates for sensitive actions.

---

## 1. System context

```mermaid
flowchart TB
  subgraph users [Users]
    Human[Operator / user]
  end

  subgraph friday [Friday platform]
    Web[Next.js web UI]
    API[FastAPI control plane]
    Agent[ADK LlmAgent runtime]
    Tools[Native tools + MCP servers]
  end

  subgraph external [External services]
    LLM[Claude models via Anthropic-compatible API]
    MCPExt[Third-party MCP servers]
    WebAPI[Web / search / social APIs]
  end

  subgraph persistence [Persistence]
    DataVol["~/.friday / /data volume"]
    Git[Git-backed self-edits]
    Vault[Encrypted credential vault]
  end

  Human -->|HTTPS chat, approvals| Web
  Web -->|REST + SSE /api/*| API
  API --> Agent
  Agent --> Tools
  Agent -->|LiteLlm| LLM
  Tools --> MCPExt
  Tools --> WebAPI
  API --> DataVol
  Tools --> Git
  Tools --> Vault
```

---

## 2. Deployment topology (production)

Single-host Docker Compose with Caddy TLS termination. The browser talks to one origin; routing splits API vs UI.

```mermaid
flowchart LR
  Browser[Browser]

  subgraph host [Docker host]
    Caddy[Caddy :443 TLS]
    Web[web container Next.js :3000]
    Backend[backend container FastAPI :8080]
    Vol[friday-data volume]
  end

  Browser -->|HTTPS otpgod.com| Caddy
  Caddy -->|/api/*| Backend
  Caddy -->|/*| Web
  Web -->|FRIDAY_API internal| Backend
  Backend --> Vol
```

| Path | Target | Purpose |
|------|--------|---------|
| `https://<host>/api/*` | `backend:8080` | REST, SSE streams, static artifacts |
| `https://<host>/*` | `web:3000` | React chat UI (proxies API in dev via `next.config.js`) |

Local dev: `python -m cli serve` on `:8080`, `npm run dev` on `:3000` with API rewrite to backend.

---

## 3. Repository layout

```mermaid
flowchart TB
  subgraph repo [hack-agent monorepo]
    WebDir["web/ — Next.js 15, React 19"]
    FridayDir["friday/ — Python 3.13 backend"]
    Deploy["deploy/ · docker-compose.yml · Caddyfile"]
    Ref["reference/hermes-agent/ — read-only design reference"]
  end

  WebDir --> ChatUI[Streaming chat + admin pages]
  FridayDir --> CP[control_plane/]
  FridayDir --> Core[core/]
  FridayDir --> ToolsMod[friday_tools/ · mcp_tools/]
  FridayDir --> Domains[domains/social_media/]
```

---

## 4. Control plane (backend)

FastAPI app (`friday/control_plane/app.py`) is the single HTTP surface for UI, CLI, and automations.

```mermaid
flowchart TB
  subgraph fastapi [FastAPI control plane]
    Routes[REST routes]
    Stream[streaming.py SSE bridge]
    Appr[approvals.py]
    Build[builder.py hot-reload]
    Dash[HTML dashboard legacy]
  end

  subgraph core_py [core/]
    Conv[conversation.run_once]
    Audit[audit JSONL + ring]
    Config[config + ~/.friday paths]
    Model[model LiteLlm routing]
    Registry[registry toolsets]
    Auto[automations scheduler]
    Tasks[tasks]
  end

  Routes --> Stream
  Routes --> Appr
  Routes --> Build
  Stream --> Conv
  Build --> Registry
  Conv --> ADK[Google ADK InMemoryRunner]
  ADK --> LiteLlm[LiteLlm → Claude hard/easy tiers]
```

### Key API surfaces (UI-facing)

| Endpoint | Role |
|----------|------|
| `POST /api/chat/stream` | Root agent chat (SSE) |
| `POST /api/agent/stream` | Named specialist agents |
| `GET/POST /api/approvals` | Human-in-the-loop queue |
| `GET /api/audit` | Structured activity log |
| `GET/POST/PUT/DELETE /api/skills` | Procedural memory (SKILL.md) |
| `GET /api/memory` | MEMORY.md + USER.md snapshot |
| `GET/POST /api/mcp` | MCP server registry |
| `POST /api/credentials` | Vault writes (never echoed to model) |
| `GET/POST /api/tasks` | Background task queue |
| `GET/POST /api/config` | Thinking, autonomy L0–L3, model display |
| `GET /api/files/*` | Read-only artifact hosting |

Optional `FRIDAY_API_TOKEN` → Bearer auth on all `/api/*` except health.

---

## 5. Agent runtime & tool model

Agents are declared in `registry/agents.json` and built by `control_plane/builder.py`.

```mermaid
flowchart TB
  Root[root agent Opus tier]

  Root --> SelfDev[self_dev read/write/edit + git]
  Root --> Skills[skills create/edit/patch]
  Root --> Delegate[spawn_subagent depth-capped]
  Root --> Sandbox[sandbox docker no-network]
  Root --> Capability[create_tool / create_mcp_server]
  Root --> Files[files web browser computer]
  Root --> Auth[request_credential vault]
  Root --> MCP[MCP toolsets from registry/mcp.json]

  Delegate --> Child[Child LlmAgent subset toolsets]
  Child --> Summary[Summary-only return to parent]

  MCP --> Callmissed[callmissed_search]
  MCP --> Metrics[metrics mock]
  MCP --> HF[huggingface / yourmemory optional]

  subgraph social [domains/social_media]
    Scout[trend_scout]
    Studio[content_studio]
    Publisher[publisher gated]
    Analyst[analyst]
    Ads[ad_manager gated]
  end

  Root -.-> social
```

**Model routing** (`core/model.py`): `classify_difficulty()` picks **hard** (Opus) vs **easy** (Sonnet) via LiteLlm against an Anthropic-compatible `/v1/messages` endpoint.

**Hot reload**: `builder.hot_reload()` bumps tool generation counter after self-edits, new tools, or MCP registration.

---

## 6. Streaming pipeline (chat UX)

The frontend contract is defined in `control_plane/streaming.py` and mirrored in `web/src/lib/types.ts`.

```mermaid
sequenceDiagram
  participant UI as Next.js page.tsx
  participant API as POST /api/chat/stream
  participant Bridge as streaming.py
  participant ADK as ADK runner
  participant LLM as Claude API

  UI->>API: JSON goal, session_id, attachments
  API->>Bridge: stream_agent()
  Bridge-->>UI: SSE start
  loop ADK events
    ADK->>LLM: messages + tools
    LLM-->>ADK: tokens / tool calls
    Bridge-->>UI: thinking / token / tool_args / tool_call
    ADK->>ADK: execute tool
    Bridge-->>UI: tool_result (+ media)
    opt nested delegation
      Bridge-->>UI: subagent_start / subagent_end
    end
  end
  Bridge-->>UI: done
  UI->>UI: applyToBlocks nested block tree
```

**UI block model**: assistant turns are ordered `Block[]` — text, thinking, tool cards, nested sub-agents, compaction markers. Events with `depth ≥ 1` route into the deepest open sub-agent container.

---

## 7. Frontend architecture

```mermaid
flowchart TB
  subgraph pages [App Router pages]
    Home["/ chat"]
    SkillsPage["/skills"]
    MemoryPage["/memory"]
    ActivityPage["/activity"]
    TasksPage["/tasks"]
    MCPPage["/mcp"]
    SettingsPage["/settings"]
  end

  subgraph components [Key components]
    Composer[Composer attachments + agent picker]
    Message[Message block renderer]
    ToolCard[ToolCard + tool-views]
    SidePanel[SidePanel approvals audit]
    Sidebar[Sidebar sessions localStorage]
  end

  subgraph lib [lib/]
    ApiTS[api.ts SSE fetch]
    TypesTS[types.ts StreamEvent]
    ChatsTS[chats.ts session persistence]
  end

  Home --> Composer
  Home --> Message
  Home --> SidePanel
  Home --> Sidebar
  Message --> ToolCard
  Home --> ApiTS
  ApiTS --> TypesTS
  Sidebar --> ChatsTS
```

- **Session storage**: chat history in `localStorage` (`friday.chats.v1`); backend continuity via `session_id`.
- **API client**: `streamChat()` parses SSE over `fetch` + `ReadableStream` (POST body).
- **Icons**: custom transparent SVG set in `web/src/components/icons/`.

---

## 8. Security & approvals

```mermaid
flowchart LR
  Tool[Sensitive tool call]
  Queue[approvals queue]
  Human[Human in UI]
  GitSnap[git snapshot]
  Vault[Encrypted vault]

  Tool -->|L0/L1 gate| Queue
  Queue --> Human
  Human -->|approve| Tool
  Human -->|reject| Audit[audit log]

  SelfEdit[self_dev write/edit] --> GitSnap
  Credential[request_credential] --> Queue
  Human -->|POST /api/credentials| Vault

  Sandbox[sandbox_exec] --> Docker[Docker no network cap-drop]
```

| Autonomy | Behavior |
|----------|----------|
| L0 | Ask everything sensitive |
| L1 | Balanced — publish, self-edit, spend gated |
| L2 | Whitelisted actions auto-approve; sensitive actions still gated |
| L3 | Full auto — no approval queue (single-user locked hosts only) |

Secrets are scrubbed from audit logs; vault values never enter model context.

---

## 9. Data & memory

```mermaid
flowchart TB
  subgraph runtime_home ["~/.friday or /data"]
    MemoryMD[MEMORY.md USER.md]
    SkillsDir[skills/ + .archive/]
    MCPGen[mcp_tools/generated/]
    CapGen[capability/generated/]
    Artifacts[artifacts/ served at /api/files]
    AuditLog[audit JSONL]
    Sessions[conversation sessions]
    VaultFile[encrypted credentials]
  end

  Curator[curator archive-only] --> SkillsDir
  MemorySnap[frozen snapshot per run] --> MemoryMD
  Prompt[prompt cache stable system prompt] --> MemorySnap
```

**Curator**: archive-only lifecycle for agent-created skills (never pinned user skills).

**Compaction**: long conversations summarized; UI shows `compaction` SSE events.

---

## 10. CLI & operations

| Command | Purpose |
|---------|---------|
| `python -m cli serve` | Uvicorn → `control_plane.app` |
| `python -m cli run "goal"` | One-shot root agent |
| `python -m cli social` | Social-media domain loop |
| `python -m cli eval` | Eval harness |
| `python -m cli curator` | Run skill curator |

CI: `.github/workflows/ci.yml` (backend tests + web build). Deploy: `.github/workflows/deploy.yml` + `docker-compose.yml`.

---

## Related docs

- Backend detail: `friday/architecture.md`
- Agent workflow: `AGENTS.md`
- SSE contract: `friday/control_plane/streaming.py` ↔ `web/src/lib/types.ts`
