"""Friday control-plane FastAPI app: dashboard + REST API.

Surfaces the agent at work:
* POST /api/run            -> run the root agent on a goal (async)
* POST /api/social         -> run the full social-media loop
* GET  /api/approvals      -> pending + recent approval queue
* POST /api/approvals/{id} -> approve/reject
* GET  /api/audit          -> recent audit events
* GET  /api/skills         -> list skills
* GET  /api/memory         -> live memory
* GET  /api/curator        -> curator status; POST /api/curator/run
* GET  /                   -> HTML dashboard

Single container, deployable to Cloud Run.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from core import audit
from control_plane import approvals, builder

app = FastAPI(title="Friday Control Plane")

# Serve agent-produced artifacts (PDFs, scripts' outputs, saved files) read-only
# at /api/files/<name>. Caddy already routes /api/* to this backend, so links
# like https://<host>/api/files/report.pdf open directly.
from fastapi.staticfiles import StaticFiles  # noqa: E402

from core.config import settings as _settings  # noqa: E402

_settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/files", StaticFiles(directory=str(_settings.artifacts_dir)), name="files")

# Seed bundled starter skills (research-report, data-analysis) on first boot.
try:
    from skills.manager import seed_builtin_skills

    seed_builtin_skills()
except Exception:  # noqa: BLE001 — never block startup on seeding
    pass

# CORS: explicit allowlist (no wildcard+credentials origin reflection). Override
# with FRIDAY_CORS_ORIGINS (comma-separated). Credentials are off — the API is
# token/bearer-authenticated, not cookie-authenticated.
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "FRIDAY_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional bearer-token auth. When FRIDAY_API_TOKEN is set, every request except
# the health check and CORS preflight must carry `Authorization: Bearer <token>`.
# Unset (default) keeps local dev open. Production deployments MUST set it.
_API_TOKEN = os.environ.get("FRIDAY_API_TOKEN", "").strip()
_AUTH_EXEMPT = {"/api/health"}


class _TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            _API_TOKEN
            and request.method != "OPTIONS"
            and request.url.path.startswith("/api/")
            and request.url.path not in _AUTH_EXEMPT
        ):
            header = request.headers.get("authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else ""
            if not _secure_eq(token, _API_TOKEN):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _secure_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())


app.add_middleware(_TokenAuthMiddleware)


# --- Access password gate ---------------------------------------------------
# When FRIDAY_ACCESS_PASSWORD is set, the whole UI/API is locked behind a single
# shared password. The frontend shows a password screen; POST /api/login issues
# an HttpOnly cookie carrying a one-way token derived from the password (the
# password itself is never stored in the cookie), and every other /api route
# requires that cookie. Empty password = open (local dev).
_ACCESS_PASSWORD = _settings.access_password
_ACCESS_COOKIE = "friday_access"
_GATE_EXEMPT = {"/api/health", "/api/login", "/api/auth", "/api/logout"}


def _access_token() -> str:
    """One-way token for the access cookie (can't be reversed to the password)."""
    import hashlib

    return hashlib.sha256(f"friday-access:{_ACCESS_PASSWORD}".encode()).hexdigest()


def _has_access(request: Request) -> bool:
    return _secure_eq(request.cookies.get(_ACCESS_COOKIE, ""), _access_token())


class _PasswordGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            _ACCESS_PASSWORD
            and request.method != "OPTIONS"
            and request.url.path.startswith("/api/")
            and request.url.path not in _GATE_EXEMPT
            and not _has_access(request)
        ):
            return JSONResponse({"error": "locked", "auth_required": True}, status_code=401)
        return await call_next(request)


app.add_middleware(_PasswordGateMiddleware)


class LoginReq(BaseModel):
    password: str = ""


@app.post("/api/login")
async def login(req: LoginReq):
    """Exchange the shared password for an access cookie."""
    if not _ACCESS_PASSWORD:
        return {"ok": True, "required": False}
    if not _secure_eq(req.password.strip(), _ACCESS_PASSWORD):
        return JSONResponse({"ok": False, "error": "wrong password"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        _ACCESS_COOKIE,
        _access_token(),
        max_age=30 * 24 * 3600,
        httponly=True,
        # Secure only when the deployment is actually served over HTTPS
        # (prod = https://otpgod.com); plain-http/local keeps it sendable.
        secure=_settings.public_url.lower().startswith("https"),
        samesite="lax",
        path="/",
    )
    return resp


@app.get("/api/auth")
async def auth_status(request: Request):
    """Whether a password is required and whether this client is authenticated."""
    if not _ACCESS_PASSWORD:
        return {"authed": True, "required": False}
    return {"authed": _has_access(request), "required": True}


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_ACCESS_COOKIE, path="/")
    return resp


@app.on_event("startup")
async def _start_automation_scheduler() -> None:
    """Tick scheduled automations every minute (cron parity with the reference)."""
    from core import automations

    async def loop() -> None:
        while True:
            try:
                await automations.tick()
            except Exception as exc:  # noqa: BLE001 — scheduler must survive
                audit.log("automation.tick_error", error=str(exc)[:200])
            await asyncio.sleep(automations.TICK_SECONDS)

    asyncio.get_running_loop().create_task(loop())
_DASHBOARD = (Path(__file__).resolve().parent / "templates" / "dashboard.html").read_text(encoding="utf-8")


class Attachment(BaseModel):
    name: str
    mime: str
    data: str  # base64


class RunReq(BaseModel):
    goal: str
    session_id: str | None = None
    attachments: list[Attachment] = []


class SocialReq(BaseModel):
    goal: str = "grow launch awareness this week"
    niche: str = "developer tools"
    brand_path: str | None = None


class DecisionReq(BaseModel):
    approve: bool


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return HTMLResponse(_DASHBOARD)


@app.post("/api/run")
async def api_run(req: RunReq):
    from core.conversation import run_once

    agent = builder.build_agent("root")
    out = await run_once(agent, req.goal)
    return {"goal": req.goal, "output": out}


# --- Background autonomous tasks (Manus-style) ------------------------------
class TaskReq(BaseModel):
    goal: str


@app.post("/api/tasks")
async def api_task_submit(req: TaskReq):
    """Launch a goal that runs autonomously in the background (survives disconnect)."""
    from core import tasks

    try:
        return tasks.submit(req.goal)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/tasks")
async def api_tasks_list():
    from core import tasks

    return {"tasks": tasks.list_tasks()}


@app.get("/api/tasks/{task_id}")
async def api_task_get(task_id: str):
    from core import tasks

    t = tasks.get_task(task_id)
    if t is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return t


@app.post("/api/chat/stream")
async def api_chat_stream(req: RunReq):
    """Stream a root-agent run as SSE: tokens, tool calls, tool results, done."""
    from control_plane.streaming import stream_agent

    async def gen():
        # Factory: only built on the first message of a conversation; later
        # messages reuse the cached runner so multi-turn context is kept.
        async for chunk in stream_agent(
            lambda: builder.build_agent("root"),
            req.goal,
            agent_name="root",
            chat_id=req.session_id,
            attachments=[a.model_dump() for a in req.attachments],
        ):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


class AgentChatReq(BaseModel):
    message: str
    agent: str = "root"
    session_id: str | None = None
    attachments: list[Attachment] = []


@app.post("/api/agent/stream")
async def api_agent_stream(req: AgentChatReq):
    """Stream a named agent (root, or a social specialist) as SSE."""
    from control_plane.streaming import stream_agent

    if req.agent == "root":
        agent = builder.build_agent("root")
    else:
        from domains.social_media import agents as A

        factory = {
            "trend_scout": A.build_trend_scout,
            "analyst": A.build_analyst,
            "publisher": A.build_publisher,
            "ad_manager": A.build_ad_manager,
        }.get(req.agent)
        if factory is None:
            agent = builder.build_agent("root")
        elif req.agent == "content_studio":
            agent = A.build_content_studio(A.load_brand())
        else:
            agent = factory()

    async def gen():
        async for chunk in stream_agent(
            agent,
            req.message,
            agent_name=req.agent,
            chat_id=req.session_id,
            attachments=[a.model_dump() for a in req.attachments],
        ):
            yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/chat/{chat_id}")
def api_chat_delete(chat_id: str):
    """Drop the cached conversation runner when the user deletes a chat."""
    from control_plane.streaming import drop_conversation

    return {"dropped": drop_conversation(chat_id)}


@app.post("/api/social")
async def api_social(req: SocialReq):
    from domains.social_media.loop import run_social_loop

    result = await run_social_loop(req.goal, req.niche, req.brand_path)
    return result


@app.get("/api/approvals")
def api_approvals():
    return {"pending": approvals.pending(), "recent": approvals.all_actions(50)}


@app.post("/api/approvals/{action_id}")
def api_decide(action_id: str, req: DecisionReq):
    entry = approvals.decide(action_id, req.approve)
    if entry is None:
        return JSONResponse({"error": "not found or not pending"}, status_code=404)
    return entry


@app.get("/api/audit")
def api_audit(limit: int = 100, prefix: str | None = None):
    return {"events": audit.recent(limit=limit, event_prefix=prefix)}


@app.get("/api/skills")
def api_skills():
    builder.import_tool_modules()
    from skills import usage
    from skills.manager import _iter_skills, _parse_frontmatter, skill_list

    items = []
    for name, md in _iter_skills():
        fm = _parse_frontmatter(md.read_text(encoding="utf-8")[:4000])
        meta = usage.get(name) or {}
        items.append(
            {
                "name": name,
                "description": fm.get("description", ""),
                "created_by": meta.get("created_by", "user"),
                "pinned": bool(meta.get("pinned")),
            }
        )
    # `skills` (text) kept for the legacy dashboard; `items` is the structured form.
    return {"skills": skill_list(), "items": items}


@app.get("/api/skills/{name}")
def api_skill_view(name: str):
    builder.import_tool_modules()
    from skills.manager import skill_view

    content = skill_view(name)
    if content.startswith("error:"):
        return JSONResponse({"error": content}, status_code=404)
    return {"name": name, "content": content}


class SkillWriteReq(BaseModel):
    content: str


@app.put("/api/skills/{name}")
def api_skill_edit(name: str, req: SkillWriteReq):
    builder.import_tool_modules()
    from skills.manager import skill_edit

    out = skill_edit(name, req.content)
    if out.startswith("error:"):
        return JSONResponse({"error": out}, status_code=400)
    audit.log("skill.edit.ui", name=name)
    return {"ok": True, "message": out}


class SkillCreateReq(BaseModel):
    name: str
    content: str


@app.post("/api/skills")
def api_skill_create(req: SkillCreateReq):
    builder.import_tool_modules()
    from skills.manager import skill_create

    out = skill_create(req.name, req.content)
    if out.startswith("error:"):
        return JSONResponse({"error": out}, status_code=400)
    audit.log("skill.create.ui", name=req.name)
    return {"ok": True, "message": out}


@app.delete("/api/skills/{name}")
def api_skill_delete(name: str):
    builder.import_tool_modules()
    from skills.manager import skill_delete

    out = skill_delete(name)
    if out.startswith("error:"):
        return JSONResponse({"error": out}, status_code=400)
    return {"ok": True, "message": out}


@app.get("/api/memory")
def api_memory():
    from memory.store import memory_show

    return {"memory": memory_show()}


@app.get("/api/curator")
def api_curator():
    from curator.curator import status

    return status()


@app.post("/api/curator/run")
def api_curator_run():
    from curator.curator import run

    return run(force=True)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "friday"}


# --- MCP server management -------------------------------------------------


class McpServerReq(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    description: str = ""
    requires: list[str] = []  # env keys the server needs (resolved env/vault)


def _mcp_path():
    from core.config import settings

    return settings.registry_dir / "mcp.json"


def _load_mcp() -> dict:
    import json

    p = _mcp_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"servers": {}}


def _save_mcp(cfg: dict) -> None:
    import json

    _mcp_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


@app.get("/api/mcp")
def api_mcp_list():
    """List registered MCP servers + which agents use them."""
    cfg = _load_mcp()
    agents = builder.load_registry("agents.json").get("agents", {})
    used_by: dict[str, list[str]] = {}
    for aname, spec in agents.items():
        for s in spec.get("mcp", []):
            used_by.setdefault(s, []).append(aname)
    servers = []
    for name, spec in cfg.get("servers", {}).items():
        servers.append(
            {
                "name": name,
                "command": spec.get("command", ""),
                "args": spec.get("args", []),
                "description": spec.get("description", ""),
                "used_by": used_by.get(name, []),
                **builder.mcp_auth_status(spec),
            }
        )
    return {"servers": servers}


@app.post("/api/mcp")
def api_mcp_add(req: McpServerReq):
    """Register a new MCP server."""
    if not req.name.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"error": "name must be alphanumeric/_/-"}, status_code=400)
    from core.osv_check import malware_advisories

    bad = malware_advisories(req.command, req.args)
    if bad:
        return JSONResponse(
            {"error": f"package blocked — known malware advisories: {', '.join(bad)} (OSV.dev)"},
            status_code=400,
        )
    cfg = _load_mcp()
    cfg.setdefault("servers", {})[req.name] = {
        "command": req.command,
        "args": req.args,
        "env": req.env,
        "description": req.description,
        "requires": req.requires,
    }
    _save_mcp(cfg)
    audit.log("mcp.added", name=req.name)
    return {"ok": True, "name": req.name, **builder.mcp_auth_status(cfg["servers"][req.name])}


@app.delete("/api/mcp/{name}")
def api_mcp_delete(name: str):
    cfg = _load_mcp()
    if name in cfg.get("servers", {}):
        del cfg["servers"][name]
        _save_mcp(cfg)
        audit.log("mcp.deleted", name=name)
        return {"ok": True}
    return JSONResponse({"error": "not found"}, status_code=404)


class McpAttachReq(BaseModel):
    server: str
    agent: str = "root"


@app.post("/api/mcp/attach")
def api_mcp_attach(req: McpAttachReq):
    """Attach an MCP server to an agent (adds to its 'mcp' list) and hot-reload."""
    import json
    from core.config import settings

    apath = settings.registry_dir / "agents.json"
    agents = builder.load_registry("agents.json")
    spec = agents.get("agents", {}).get(req.agent)
    if spec is None:
        return JSONResponse({"error": f"agent {req.agent} not found"}, status_code=404)
    mcp_list = spec.setdefault("mcp", [])
    if req.server not in mcp_list:
        mcp_list.append(req.server)
    apath.write_text(json.dumps(agents, indent=2), encoding="utf-8")
    builder.hot_reload()
    audit.log("mcp.attached", server=req.server, agent=req.agent)
    return {"ok": True, "agent": req.agent, "mcp": mcp_list}


@app.post("/api/mcp/test/{name}")
async def api_mcp_test(name: str):
    """Connect to an MCP server and list its tools (validates the config)."""
    cfg = _load_mcp().get("servers", {}).get(name)
    if not cfg:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
        from mcp import StdioServerParameters

        from sandbox.docker_env import _scrubbed_env

        # Never hand the full host environment (incl. API keys) to a spawned
        # MCP process. Start from a scrubbed baseline + the declared env +
        # vault credentials for the keys this server explicitly requires.
        from auth import vault

        child_env = {**_scrubbed_env(), **(cfg.get("env") or {})}
        missing: list[str] = []
        for key in cfg.get("requires") or []:
            val = child_env.get(key) or os.environ.get(key) or vault.get_credential(key)
            if val:
                child_env[key] = val
            else:
                missing.append(key)
        if missing:
            return {
                "ok": False,
                "needs_auth": True,
                "missing": missing,
                "error": f"missing credentials: {', '.join(missing)} — add them in the MCP panel",
            }
        params = StdioServerParameters(
            command=cfg["command"], args=cfg.get("args", []), env=child_env
        )
        ts = MCPToolset(connection_params=StdioConnectionParams(server_params=params))
        tools = await ts.get_tools()
        names = [t.name for t in tools]
        await ts.close()
        return {"ok": True, "tools": names}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:400]}


class AutomationReq(BaseModel):
    name: str
    goal: str
    interval_minutes: int = 60


@app.get("/api/automations")
def api_automations_list():
    from core import automations

    return {"jobs": automations.load_jobs()}


@app.post("/api/automations")
def api_automations_add(req: AutomationReq):
    from core import automations

    job = automations.add_job(req.name, req.goal, req.interval_minutes, created_by="user")
    if isinstance(job, str):
        return JSONResponse({"error": job}, status_code=400)
    return {"ok": True, "job": job}


@app.delete("/api/automations/{job_id}")
def api_automations_delete(job_id: str):
    from core import automations

    if automations.remove_job(job_id):
        return {"ok": True}
    return JSONResponse({"error": "not found"}, status_code=404)


class CredentialReq(BaseModel):
    key: str
    value: str


@app.get("/api/credentials")
def api_credentials_list():
    """Names of stored credentials (values are never returned)."""
    from auth import vault

    return {"keys": vault.list_credentials()}


@app.post("/api/credentials")
def api_credentials_set(req: CredentialReq):
    """Store a secret in the encrypted vault and resolve matching requests.

    The value is never echoed back, logged, or shown to the model — tools read
    it from the vault at call time.
    """
    from auth import vault

    key = req.key.strip()
    if not key or not req.value.strip():
        return JSONResponse({"error": "key and value are required"}, status_code=400)
    vault.set_credential(key, req.value.strip())
    # Auto-approve any pending credential request asking for this key.
    resolved = []
    for entry in approvals.pending():
        if entry["type"] == "credential" and entry.get("payload", {}).get("key_name") == key:
            approvals.decide(entry["id"], approve=True)
            approvals.mark_applied(entry["id"])
            resolved.append(entry["id"])
    audit.log("credential.stored", key=key, resolved=len(resolved))
    return {"ok": True, "key": key, "resolved_requests": resolved}


@app.delete("/api/credentials/{key}")
def api_credentials_delete(key: str):
    from auth import vault

    if vault.delete_credential(key):
        audit.log("credential.deleted", key=key)
        return {"ok": True}
    return JSONResponse({"error": "not found"}, status_code=404)


class ConfigReq(BaseModel):
    thinking: bool | None = None
    autonomy: str | None = None


@app.get("/api/config")
def api_config_get():
    from core.config import settings

    return {
        "thinking": settings.thinking,
        "autonomy": settings.autonomy,
        "model_hard": settings.model_hard,
        "model_easy": settings.model_easy,
    }


@app.post("/api/config")
def api_config_set(req: ConfigReq):
    """Update runtime settings (thinking on/off, autonomy level) and hot-reload."""
    from core.config import settings

    # Settings is a frozen dataclass; this endpoint is the one sanctioned
    # runtime override (audited, and hot_reload() rebuilds agents below).
    if req.thinking is not None:
        object.__setattr__(settings, "thinking", req.thinking)
        audit.log("config.thinking", value=req.thinking)
    if req.autonomy is not None:
        object.__setattr__(settings, "autonomy", req.autonomy)
        audit.log("config.autonomy", value=req.autonomy)
    builder.hot_reload()
    return api_config_get()
