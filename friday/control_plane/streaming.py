"""Streaming bridge: ADK agent events -> normalized UI events (SSE).

Turns a single agent run into a live stream of typed events the Cursor-style
frontend renders in real time:

  {"type": "start",          "agent": "root"}
  {"type": "thinking_start", "agent": "..."}
  {"type": "thinking",       "text": "...", "agent": "..."}   # reasoning tokens
  {"type": "thinking_end",   "agent": "..."}
  {"type": "token",          "text": "...", "agent": "..."}
  {"type": "tool_call",    "id": "...", "name": "web_search", "args": {...}}
  {"type": "tool_result",  "id": "...", "name": "web_search", "result": "...", "ok": true}
  {"type": "message",      "text": "<full assistant text>"}
  {"type": "done",         "tool_calls": N, "chars": M}
  {"type": "error",        "message": "..."}

Each tool call gets a stable id so the UI can match call->result and animate the
card from running -> done.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner
from google.genai import types

from core import audit


def _sse(event: dict[str, Any]) -> str:
    """Format a dict as a Server-Sent Event 'data:' line."""
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


class _ThinkTagFilter:
    """Split streamed text into (is_thought, text) segments.

    The local endpoint sometimes inlines reasoning as literal
    ``<thinking>…</thinking>`` tags in the answer text instead of structured
    thought parts. Tags may be split across stream deltas, so a suffix that
    could be the start of a tag is held back until the next ``feed``.
    """

    _OPEN = "<thinking>"
    _CLOSE = "</thinking>"

    def __init__(self) -> None:
        self._buf = ""
        self.in_thought = False

    def feed(self, text: str) -> list[tuple[bool, str]]:
        self._buf += text
        out: list[tuple[bool, str]] = []
        while self._buf:
            tag = self._CLOSE if self.in_thought else self._OPEN
            idx = self._buf.find(tag)
            if idx != -1:
                if idx:
                    out.append((self.in_thought, self._buf[:idx]))
                self._buf = self._buf[idx + len(tag) :]
                self.in_thought = not self.in_thought
                continue
            keep = self._partial_suffix(self._buf, tag)
            emit = self._buf[: len(self._buf) - keep]
            if emit:
                out.append((self.in_thought, emit))
            self._buf = self._buf[len(self._buf) - keep :]
            break
        return out

    def flush(self) -> list[tuple[bool, str]]:
        """Emit any held-back text (e.g. a lone ``<thin`` that never closed)."""
        out = [(self.in_thought, self._buf)] if self._buf else []
        self._buf = ""
        return out

    @staticmethod
    def _partial_suffix(s: str, tag: str) -> int:
        for n in range(min(len(tag) - 1, len(s)), 0, -1):
            if s.endswith(tag[:n]):
                return n
        return 0


# Per-stream tool-arg routing. ADK aggregates tool-call arguments and only
# surfaces the finished call, so a long file edit is invisible while the model
# writes it. litellm's raw stream chunks DO carry the argument fragments — we
# tee them to the CURRENT stream's queue so the UI can render a live "writing
# the edit…" preview. These are contextvars (not a global set) so concurrent
# chats never receive each other's tool-arg fragments.
_ROOT_SINK: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "root_arg_sink", default=None
)
# When a sub-agent is running, its events are forwarded to the parent stream
# through this sink (set in the parent's runner task, inherited by the tool call
# that spawns the child). ``_CURRENT_DEPTH`` tells the tee which nesting level a
# tool-arg fragment belongs to so it lands in the right (sub-)agent's card.
_SUBAGENT_SINK: contextvars.ContextVar[asyncio.Queue | None] = contextvars.ContextVar(
    "subagent_sink", default=None
)
_CURRENT_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("stream_depth", default=0)


def _install_litellm_tee() -> None:
    """Wrap ``litellm.acompletion`` once so streamed tool-call argument
    fragments are routed to the current stream's queue without disturbing ADK."""
    import litellm

    if getattr(litellm, "_friday_arg_tee", False):
        return
    orig = litellm.acompletion

    async def acompletion_tee(*args: Any, **kwargs: Any):
        res = await orig(*args, **kwargs)
        if not kwargs.get("stream"):
            return res
        # Capture the routing target from THIS call's context (the request is
        # issued inside the runner task that set these vars).
        depth = _CURRENT_DEPTH.get()
        sub_sink = _SUBAGENT_SINK.get()
        root_sink = _ROOT_SINK.get()

        async def tee():
            names: dict[int, str] = {}
            async for chunk in res:
                try:
                    delta = chunk.choices[0].delta
                    for tc in getattr(delta, "tool_calls", None) or []:
                        idx = getattr(tc, "index", 0) or 0
                        fn = getattr(tc, "function", None)
                        if fn is None:
                            continue
                        if getattr(fn, "name", None):
                            names[idx] = fn.name
                        frag = getattr(fn, "arguments", None)
                        tool = names.get(idx)
                        if not (tool and frag):
                            continue
                        payload = {"name": tool, "delta": str(frag)[:4000]}
                        # Child tool-args ride the sub-agent sink (in order with
                        # the child's other events); root args go to this
                        # stream's own queue only — never broadcast.
                        if depth > 0 and sub_sink is not None:
                            sub_sink.put_nowait({"type": "tool_args", **payload, "depth": depth})
                        elif root_sink is not None:
                            root_sink.put_nowait(payload)
                except (AttributeError, IndexError, TypeError):
                    pass
                yield chunk

        return tee()

    litellm.acompletion = acompletion_tee
    litellm._friday_arg_tee = True


# Live conversations: chat_id -> (runner, adk_session_id). Reusing the runner
# keeps the FULL multi-turn context (messages, tool calls, files read/edited)
# across requests instead of starting fresh every message.
_CONVERSATIONS: dict[str, tuple[InMemoryRunner, str]] = {}
_MAX_CONVERSATIONS = 50


AgentOrFactory = LlmAgent | Callable[[], LlmAgent]


async def _conversation_for(
    chat_id: str | None, agent: AgentOrFactory, agent_name: str, app_name: str, user_id: str
) -> tuple[InMemoryRunner, str]:
    if chat_id:
        cached = _CONVERSATIONS.get(f"{chat_id}:{agent_name}")
        if cached is not None:
            return cached
    # Only materialize the agent on a cache miss — building attaches MCP
    # toolsets (subprocesses), so cached conversations must not rebuild.
    resolved = agent() if callable(agent) else agent
    runner = InMemoryRunner(agent=resolved, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id=user_id)
    if chat_id:
        while len(_CONVERSATIONS) >= _MAX_CONVERSATIONS:
            _CONVERSATIONS.pop(next(iter(_CONVERSATIONS)))  # evict oldest
        _CONVERSATIONS[f"{chat_id}:{agent_name}"] = (runner, session.id)
    return runner, session.id


def _pdf_text(data: bytes) -> str:
    """Extract text from a PDF (litellm/Anthropic proxies vary on native PDF
    support, so text extraction is the portable path)."""
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages[:50])
    except Exception as exc:  # noqa: BLE001
        return f"(could not extract PDF text: {exc})"


def _attachment_parts(attachments: list[dict[str, Any]] | None) -> list[types.Part]:
    """User uploads -> model-visible parts.

    EVERY uploaded file (any type) is saved into the agent's file area under
    ``uploads/`` so the agent can read/process it with the files tools or
    run_python. Images are also shown inline (native vision); PDFs and text are
    also previewed inline. The agent is told the saved paths.
    """
    import base64
    import os

    from core.config import settings

    parts: list[types.Part] = []
    saved: list[str] = []
    updir = settings.file_root / "uploads"
    try:
        updir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    for att in (attachments or [])[:8]:
        try:
            mime = str(att.get("mime") or "application/octet-stream")
            data = base64.b64decode(att.get("data") or "")
            fname = os.path.basename(str(att.get("name") or "attachment")).replace("\\", "_") or "attachment"
        except (ValueError, TypeError):
            continue
        if not data:
            continue
        # Save locally so the agent can read ANY type later.
        try:
            (updir / fname).write_bytes(data)
            saved.append(f"uploads/{fname}")
        except OSError:
            pass
        # Inline preview for the common types the model reads directly.
        if mime.startswith("image/"):
            parts.append(types.Part(inline_data=types.Blob(mime_type=mime, data=data)))
        elif mime == "application/pdf" or fname.lower().endswith(".pdf"):
            parts.append(
                types.Part(text=f"[Attached PDF {fname!r} — extracted text]\n{_pdf_text(data)[:40000]}")
            )
        elif mime.startswith("text/") or fname.lower().endswith(
            (".md", ".txt", ".csv", ".json", ".py", ".ts", ".js", ".html",
             ".xml", ".yaml", ".yml", ".log", ".tsv", ".ini", ".toml")
        ):
            parts.append(
                types.Part(
                    text=f"[Attached file {fname!r}]\n{data.decode('utf-8', 'replace')[:40000]}"
                )
            )
    if saved:
        parts.append(
            types.Part(
                text="[Uploaded files were saved to your file area — read or process any of "
                "them (any type: xlsx, docx, zip, audio, etc.) with the files tools or "
                "run_python:\n" + "\n".join(f"- {p}" for p in saved) + "\n]"
            )
        )
    return parts


def drop_conversation(chat_id: str) -> int:
    """Forget cached runners for a chat (e.g. when the user deletes it)."""
    stale = [k for k in _CONVERSATIONS if k.startswith(f"{chat_id}:")]
    for k in stale:
        _CONVERSATIONS.pop(k, None)
    return len(stale)


def subagent_sink() -> asyncio.Queue | None:
    """The active sub-agent event sink, if a parent stream is forwarding."""
    return _SUBAGENT_SINK.get()


async def stream_child(
    child: LlmAgent,
    task: str,
    *,
    sink: asyncio.Queue,
    depth: int,
    tier: str = "",
    role: str = "leaf",
) -> str:
    """Run a sub-agent and forward its activity to ``sink`` as depth-tagged UI
    events, returning the child's final text.

    Emits ``subagent_start`` / ``subagent_end`` around a live stream of the
    child's thinking, tokens, tool calls and results — so the UI can render the
    child's work nested inside the parent (Cursor-style), instead of a single
    opaque ``spawn_subagent`` card. Nested children just push to the same sink
    with a higher ``depth``.
    """
    sub_id = uuid.uuid4().hex[:8]
    sink.put_nowait(
        {
            "type": "subagent_start",
            "id": sub_id,
            "agent": child.name,
            "depth": depth,
            "task": task[:300],
            "role": role,
            "tier": tier,
        }
    )

    runner = InMemoryRunner(agent=child, app_name="friday-sub")
    session = await runner.session_service.create_session(app_name="friday-sub", user_id="sub")
    msg = types.Content(role="user", parts=[types.Part(text=task)])
    cfg = RunConfig(streaming_mode=StreamingMode.SSE)

    full: list[str] = []
    call_ids: dict[str, list[str]] = {}
    tagf = _ThinkTagFilter()
    thinking_open = False
    emitted_thinking = False

    def push(ev: dict[str, Any]) -> None:
        ev.setdefault("depth", depth)
        ev.setdefault("agent", child.name)
        sink.put_nowait(ev)

    # Run the child at depth+? — set so the tee tags its tool-args correctly and
    # any grandchildren inherit a deeper level.
    dtok = _CURRENT_DEPTH.set(depth)
    try:
        async for ev in runner.run_async(
            user_id="sub", session_id=session.id, new_message=msg, run_config=cfg
        ):
            if not (ev.content and ev.content.parts):
                continue
            for part in ev.content.parts:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    if thinking_open:
                        push({"type": "thinking_end"})
                        thinking_open = False
                    cid = uuid.uuid4().hex[:8]
                    call_ids.setdefault(fc.name, []).append(cid)
                    push(
                        {
                            "type": "tool_call",
                            "id": cid,
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        }
                    )
                    continue
                fr = getattr(part, "function_response", None)
                if fr is not None:
                    queue = call_ids.get(fr.name) or []
                    cid = queue.pop(0) if queue else uuid.uuid4().hex[:8]
                    rtext = _coerce_result(fr.response)
                    result_ev: dict[str, Any] = {
                        "type": "tool_result",
                        "id": cid,
                        "name": fr.name,
                        "result": rtext[:8000],
                        "ok": "error" not in rtext.lower()[:30],
                    }
                    media = _extract_media(fr.response) or _media_from_paths(rtext)
                    if media:
                        result_ev["media"] = media
                    push(result_ev)
                    emitted_thinking = False
                    continue
                text = getattr(part, "text", None)
                if not text:
                    continue
                if getattr(part, "thought", False):
                    if not ev.partial and emitted_thinking:
                        continue
                    if ev.partial:
                        emitted_thinking = True
                    if not thinking_open:
                        thinking_open = True
                        push({"type": "thinking_start"})
                    push({"type": "thinking", "text": text})
                    continue
                if ev.partial:
                    for is_th, seg in tagf.feed(text):
                        if is_th:
                            if not thinking_open:
                                thinking_open = True
                                push({"type": "thinking_start"})
                            push({"type": "thinking", "text": seg})
                        else:
                            if thinking_open:
                                push({"type": "thinking_end"})
                                thinking_open = False
                            full.append(seg)
                            push({"type": "token", "text": seg})
        for is_th, seg in tagf.flush():
            if is_th:
                push({"type": "thinking", "text": seg})
            else:
                full.append(seg)
                push({"type": "token", "text": seg})
        if thinking_open:
            push({"type": "thinking_end"})
    finally:
        _CURRENT_DEPTH.reset(dtok)
        result = "".join(full).strip()
        sink.put_nowait(
            {"type": "subagent_end", "id": sub_id, "agent": child.name, "depth": depth}
        )

    return result or "(sub-agent returned no output)"


async def stream_agent(
    agent: AgentOrFactory,
    user_text: str,
    *,
    user_id: str = "u",
    app_name: str = "friday",
    chat_id: str | None = None,
    agent_name: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> AsyncIterator[str]:
    """Run ``agent`` and yield SSE-formatted normalized UI events.

    Pass ``chat_id`` to keep one continuous ADK session per conversation —
    every later message sees the prior turns and tool results. ``agent`` may be
    a factory so cached conversations skip the (expensive) agent build; pass
    ``agent_name`` alongside a factory for the cache key.
    """
    name = agent.name if isinstance(agent, LlmAgent) else (agent_name or "root")
    runner, session_id = await _conversation_for(chat_id, agent, name, app_name, user_id)
    name = runner.agent.name
    msg = types.Content(
        role="user", parts=[types.Part(text=user_text), *_attachment_parts(attachments)]
    )
    cfg = RunConfig(streaming_mode=StreamingMode.SSE)

    yield _sse({"type": "start", "agent": name})

    # Compact the running conversation if it has grown past the context limit,
    # BEFORE this turn runs — keeps long sessions inside the window. Best-effort:
    # any failure just skips compaction (the turn still runs).
    try:
        from core.compaction import maybe_compact

        info = await maybe_compact(runner, session_id, user_id=user_id, app_name=app_name)
        if info:
            yield _sse({"type": "compaction", "agent": name, **info})
    except Exception as exc:  # noqa: BLE001
        audit.log("compaction.error", error=str(exc)[:200])

    full_text: list[str] = []
    tool_calls = 0
    emitted_first_token = False
    emitted_thinking = False
    thinking_open = False
    # Map ADK function_call name -> FIFO of generated ids (parallel calls to the
    # same tool must not collide; results arrive in call order per name).
    call_ids: dict[str, list[str]] = {}
    tag_filter = _ThinkTagFilter()

    def _text_events(segs: list[tuple[bool, str]], author: str, *, streamed: bool) -> list[dict[str, Any]]:
        """Turn filtered (is_thought, text) segments into UI events."""
        nonlocal thinking_open, emitted_thinking
        events: list[dict[str, Any]] = []
        for is_th, seg in segs:
            if is_th:
                if not thinking_open:
                    thinking_open = True
                    events.append({"type": "thinking_start", "agent": author})
                emitted_thinking = True
                events.append({"type": "thinking", "text": seg, "agent": author})
            else:
                if thinking_open:
                    events.append({"type": "thinking_end", "agent": author})
                    thinking_open = False
                full_text.append(seg)
                events.append(
                    {"type": "token" if streamed else "message", "text": seg, "agent": author}
                )
        return events

    # Merge producers into one stream: ADK events + live tool-arg deltas +
    # sub-agent events forwarded from any spawn_subagent call this turn.
    _install_litellm_tee()
    arg_q: asyncio.Queue = asyncio.Queue()
    out_q: asyncio.Queue = asyncio.Queue()
    sub_q: asyncio.Queue = asyncio.Queue()

    async def _pump_runner() -> None:
        # Set inside the runner task so the contextvars are visible to the tool
        # calls it drives — that's how spawn_subagent finds the sink to forward
        # its child's events, how the tee tags nested tool-args, and how root
        # tool-args route to THIS stream only (never broadcast).
        _ROOT_SINK.set(arg_q)
        _SUBAGENT_SINK.set(sub_q)
        _CURRENT_DEPTH.set(0)
        try:
            async for ev in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=msg, run_config=cfg
            ):
                await out_q.put(("ev", ev))
            await out_q.put(("end", None))
        except Exception as exc:  # noqa: BLE001 — re-raised in the consumer
            await out_q.put(("err", exc))

    async def _pump_args() -> None:
        while True:
            await out_q.put(("args", await arg_q.get()))

    async def _pump_sub() -> None:
        while True:
            await out_q.put(("sub", await sub_q.get()))

    runner_task = asyncio.create_task(_pump_runner())
    args_task = asyncio.create_task(_pump_args())
    sub_task = asyncio.create_task(_pump_sub())

    try:
        while True:
            kind, payload = await out_q.get()
            if kind == "end":
                # Drain any sub-agent/tool-arg events still queued (they ride
                # separate queues than the runner, so a child's trailing tokens
                # or its subagent_end can be in flight when the runner ends).
                for q in (sub_q, arg_q):
                    while not q.empty():
                        item = q.get_nowait()
                        if q is sub_q:
                            yield _sse(item)
                        else:
                            yield _sse(
                                {
                                    "type": "tool_args",
                                    "name": item["name"],
                                    "delta": item["delta"],
                                    "agent": name,
                                }
                            )
                break
            if kind == "err":
                raise payload
            if kind == "args":
                yield _sse(
                    {
                        "type": "tool_args",
                        "name": payload["name"],
                        "delta": payload["delta"],
                        "agent": name,
                    }
                )
                continue
            if kind == "sub":
                # A sub-agent event already shaped as a UI event — forward as-is.
                yield _sse(payload)
                continue
            ev = payload
            author = getattr(ev, "author", name)
            if ev.content and ev.content.parts:
                for part in ev.content.parts:
                    # 1. function call -> tool_call event (running)
                    fc = getattr(part, "function_call", None)
                    if fc is not None:
                        for e in _text_events(tag_filter.flush(), author, streamed=True):
                            yield _sse(e)
                        if thinking_open:
                            yield _sse({"type": "thinking_end", "agent": author})
                            thinking_open = False
                        tool_calls += 1
                        cid = uuid.uuid4().hex[:8]
                        call_ids.setdefault(fc.name, []).append(cid)
                        args = dict(fc.args) if fc.args else {}
                        audit.log("stream.tool_call", agent=author, tool=fc.name)
                        yield _sse(
                            {
                                "type": "tool_call",
                                "id": cid,
                                "name": fc.name,
                                "args": args,
                                "agent": author,
                            }
                        )
                        continue
                    # 2. function response -> tool_result event (done)
                    fr = getattr(part, "function_response", None)
                    if fr is not None:
                        queue = call_ids.get(fr.name) or []
                        cid = queue.pop(0) if queue else uuid.uuid4().hex[:8]
                        resp = fr.response
                        result_text = _coerce_result(resp)
                        ok = "error" not in result_text.lower()[:30]
                        result_ev: dict[str, Any] = {
                            "type": "tool_result",
                            "id": cid,
                            "name": fr.name,
                            "result": result_text[:8000],
                            "ok": ok,
                            "agent": author,
                        }
                        media = _extract_media(resp) or _media_from_paths(result_text)
                        if media:
                            result_ev["media"] = media
                        yield _sse(result_ev)
                        # A tool result starts a fresh LLM turn — its thinking
                        # must stream/dedupe independently of earlier turns.
                        emitted_thinking = False
                        continue
                    # 3. text -> thinking, token (streaming), or full message
                    text = getattr(part, "text", None)
                    if text:
                        is_thought = bool(getattr(part, "thought", False))
                        if is_thought:
                            # Skip the final non-partial aggregate if we already
                            # streamed this thought incrementally (mirrors text).
                            if not ev.partial and emitted_thinking:
                                continue
                            if ev.partial:
                                emitted_thinking = True
                            if not thinking_open:
                                thinking_open = True
                                yield _sse({"type": "thinking_start", "agent": author})
                            yield _sse({"type": "thinking", "text": text, "agent": author})
                            continue
                        # Regular answer text: route through the tag filter so
                        # inline <thinking>…</thinking> renders as a thinking
                        # block instead of leaking into the answer.
                        if ev.partial:
                            emitted_first_token = True
                            for e in _text_events(tag_filter.feed(text), author, streamed=True):
                                yield _sse(e)
                        else:
                            # Non-partial text: a complete message block.
                            if not full_text:
                                f = _ThinkTagFilter()
                                segs = [*f.feed(text), *f.flush()]
                                for e in _text_events(segs, author, streamed=False):
                                    yield _sse(e)
        for e in _text_events(tag_filter.flush(), name, streamed=True):
            yield _sse(e)
        if thinking_open:
            yield _sse({"type": "thinking_end", "agent": name})
        final = "".join(full_text).strip()
        audit.log("stream.done", agent=name, tool_calls=tool_calls, chars=len(final))
        yield _sse({"type": "done", "tool_calls": tool_calls, "chars": len(final)})
    except Exception as exc:  # noqa: BLE001
        audit.log("stream.error", agent=name, error=str(exc)[:300])
        yield _sse({"type": "error", "message": str(exc)[:500]})
    finally:
        # Cancel the pump tasks AND await them so a client disconnect doesn't
        # leave the ADK run / MCP subprocesses dangling ("Task was destroyed
        # but it is pending"). gather swallows the CancelledErrors.
        for t in (args_task, sub_task, runner_task):
            t.cancel()
        try:
            await asyncio.gather(args_task, sub_task, runner_task, return_exceptions=True)
        except Exception:  # noqa: BLE001
            pass


def _coerce_result(resp: Any) -> str:
    """Tool responses come back in varied shapes; normalize to a string."""
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        # ADK often wraps as {"result": ...}
        if "result" in resp and len(resp) == 1:
            return _coerce_result(resp["result"])
        return json.dumps(resp, ensure_ascii=False, default=str)
    return str(resp)


_MAX_MEDIA_ITEMS = 4
_MAX_HTML_CHARS = 200_000
_MAX_IMAGE_B64 = 4_000_000  # ~3 MB decoded

_IMG_PATH_RE = None  # compiled lazily


def _media_from_paths(result_text: str) -> dict[str, Any] | None:
    """Render images that tools saved to disk (e.g. generate_image).

    Tools return small text results (keeping base64 out of the model's
    context); the bridge spots image paths under the Friday home dir and
    inlines them for the UI only.
    """
    global _IMG_PATH_RE
    import base64
    import re
    from pathlib import Path

    from core.config import settings

    if _IMG_PATH_RE is None:
        _IMG_PATH_RE = re.compile(r"(/[^\s'\"]+\.(?:png|jpe?g|webp|gif))", re.IGNORECASE)
    home = settings.home.resolve()
    images: list[dict[str, str]] = []
    for raw in _IMG_PATH_RE.findall(result_text or "")[:_MAX_MEDIA_ITEMS]:
        try:
            p = Path(raw).resolve()
            p.relative_to(home)  # only files inside the agent home
            if not p.is_file() or p.stat().st_size > _MAX_IMAGE_B64 * 3 // 4:
                continue
            ext = p.suffix.lower().lstrip(".")
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, f"image/{ext}")
            images.append({"mime": mime, "data": base64.b64encode(p.read_bytes()).decode("ascii")})
        except (OSError, ValueError):
            continue
    return {"images": images, "html": []} if images else None


def _extract_media(resp: Any) -> dict[str, Any] | None:
    """Pull renderable media (images, interactive HTML) out of an MCP result.

    MCP servers return ``{"content": [{"type": "image", "data": b64, …},
    {"type": "resource", "resource": {"mimeType": "text/html", "text": …}}]}``.
    Flattening those into the text result destroys them; surface them as a
    structured ``media`` payload the UI renders (img / sandboxed iframe).
    """
    payload = resp
    if isinstance(payload, dict) and "result" in payload and len(payload) == 1:
        payload = payload["result"]
    if isinstance(payload, str) and payload.lstrip().startswith("{"):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return None
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None

    images: list[dict[str, str]] = []
    html: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image" and item.get("data"):
            if len(images) < _MAX_MEDIA_ITEMS and len(str(item["data"])) <= _MAX_IMAGE_B64:
                images.append({"mime": str(item.get("mimeType") or "image/png"), "data": str(item["data"])})
        elif item.get("type") == "resource":
            res = item.get("resource") or {}
            mime = str(res.get("mimeType") or "")
            text = res.get("text")
            if mime == "text/html" and text and len(html) < _MAX_MEDIA_ITEMS:
                html.append(str(text)[:_MAX_HTML_CHARS])
    if not images and not html:
        return None
    return {"images": images, "html": html}
