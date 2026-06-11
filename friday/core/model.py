"""Model factory + difficulty routing for Friday.

All agents reason through a local Anthropic-protocol endpoint via ADK's
``LiteLlm`` wrapper. Two tiers:

* ``hard`` -> Opus (deep reasoning, planning, self-edits)
* ``easy`` -> Sonnet (mechanical / tool-driven sub-tasks)

``classify_difficulty`` picks a tier from a task description using cheap
heuristics; agents may also force a tier.
"""

from __future__ import annotations

import functools
import re
from typing import Literal

from google.adk.models.lite_llm import LiteLlm

from core.config import settings

Tier = Literal["easy", "hard"]


def _normalize_model_id(model_id: str) -> str:
    """Ensure a LiteLLM-routable id. Local endpoint speaks Anthropic protocol."""
    if "/" in model_id:
        return model_id
    return f"anthropic/{model_id}"


@functools.lru_cache(maxsize=16)
def _make_gemini_llm_cached(
    model_id: str, api_key: str, max_tokens: int, thinking: bool, thinking_budget: int,
) -> LiteLlm:
    """Build a LiteLlm routed to the Gemini Developer API (AI Studio).

    Uses a plain API key (``GEMINI_API_KEY``) — no service account, so it runs
    anywhere (e.g. an EC2 box) without GCP credential files. Thinking is
    forwarded via LiteLLM's unified ``thinking`` param so Gemini returns thought
    parts (rendered as the UI's "thinking" section).
    """
    routable = model_id if "/" in model_id else f"gemini/{model_id}"
    kwargs: dict = {
        "model": routable,
        "api_key": api_key,
        "max_tokens": max_tokens,
    }
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        kwargs["allowed_openai_params"] = ["thinking"]
    return LiteLlm(**kwargs)


@functools.lru_cache(maxsize=16)
def _make_vertex_llm_cached(
    model_id: str, project: str, location: str, max_tokens: int,
    thinking: bool, thinking_budget: int,
) -> LiteLlm:
    """Build a LiteLlm routed to Vertex AI (Gemini).

    LiteLLM authenticates to Vertex via Application Default Credentials (a
    service account on Cloud Run, or ``gcloud auth application-default login``
    locally). When ``thinking`` is on, we forward LiteLLM's unified ``thinking``
    param, which maps to Gemini's ``thinkingConfig`` with ``includeThoughts`` so
    reasoning is streamed back as thought parts (rendered as the UI's "thinking"
    section). ``max_tokens`` is set generously so thinking + answer both fit.
    """
    routable = model_id if "/" in model_id else f"vertex_ai/{model_id}"
    kwargs: dict = {
        "model": routable,
        "vertex_location": location or "global",
        "max_tokens": max_tokens,
    }
    if project:
        kwargs["vertex_project"] = project
    if thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        kwargs["allowed_openai_params"] = ["thinking"]
    return LiteLlm(**kwargs)


@functools.lru_cache(maxsize=16)
def _make_llm_cached(model_id: str, base_url: str, api_key: str, thinking: bool) -> LiteLlm:
    kwargs: dict = {
        "model": _normalize_model_id(model_id),
        "api_base": base_url,
        "api_key": api_key,
    }
    if thinking:
        # Local endpoint speaks the Anthropic protocol. litellm drops unknown
        # params under drop_params=true, so we must explicitly allow `thinking`
        # to pass through, and request extended thinking with a token budget.
        # Without this the endpoint returns no reasoning blocks and the UI shows
        # no "thinking" stream. (Verified: 30 thought parts vs 0 without it.)
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": settings.thinking_budget,
        }
        kwargs["max_tokens"] = settings.max_tokens
        kwargs["allowed_openai_params"] = ["thinking"]
    return LiteLlm(**kwargs)


def _with_thinking(model_id: str) -> str:
    """Return the -thinking variant of a model id (idempotent)."""
    return model_id if model_id.endswith("-thinking") else f"{model_id}-thinking"


def make_llm(tier: Tier = "easy", *, thinking: bool | None = None) -> LiteLlm:
    """Return a (cached) LiteLlm for the given tier.

    Honors FRIDAY_FORCE_TIER. If ``thinking`` is True (or FRIDAY_THINKING=1 and
    not explicitly disabled), uses the model's ``-thinking`` variant so the
    stream surfaces reasoning.
    """
    forced = settings.force_tier.lower().strip()
    if forced in ("easy", "hard"):
        tier = forced  # type: ignore[assignment]
    model_id = settings.model_hard if tier == "hard" else settings.model_easy
    # Vertex AI (Gemini): route through LiteLLM's vertex_ai provider. No
    # Anthropic-style thinking budget and no ``-thinking`` model variant — Gemini
    # handles reasoning natively.
    if settings.llm_provider == "gemini":
        use_thinking = settings.thinking if thinking is None else thinking
        return _make_gemini_llm_cached(
            model_id, settings.gemini_api_key, settings.max_tokens,
            use_thinking, settings.thinking_budget,
        )
    if settings.llm_provider == "vertex":
        use_thinking = settings.thinking if thinking is None else thinking
        return _make_vertex_llm_cached(
            model_id, settings.vertex_project, settings.vertex_location,
            settings.max_tokens, use_thinking, settings.thinking_budget,
        )
    use_thinking = settings.thinking if thinking is None else thinking
    if use_thinking:
        model_id = _with_thinking(model_id)
    return _make_llm_cached(model_id, settings.llm_base_url, settings.llm_api_key, use_thinking)


# --- difficulty classification ---------------------------------------------

# Signals that a task warrants the stronger (Opus) tier.
_HARD_PATTERNS = [
    r"\bplan\b", r"\bdesign\b", r"\barchitect", r"\bstrateg", r"\bsynthesiz",
    r"\bdecide\b", r"\bdecision\b", r"\breconcile\b", r"\bdebug\b", r"\brefactor\b",
    r"\bbudget\b", r"\bspend\b", r"\ballocat", r"\bmulti-step\b", r"\bambiguous\b",
    r"\bedit (its|your|the) own\b", r"\bself-?edit\b", r"\borchestrat",
    r"\banalyz", r"\bevaluat", r"\bcompare\b", r"\btrade-?off",
]
_HARD_RE = re.compile("|".join(_HARD_PATTERNS), re.IGNORECASE)


def classify_difficulty(task_text: str) -> Tier:
    """Cheap heuristic tier classifier.

    Returns ``"hard"`` for planning/synthesis/decision/spend tasks or long,
    multi-clause prompts; ``"easy"`` otherwise.
    """
    text = (task_text or "").strip()
    if not text:
        return "easy"
    if _HARD_RE.search(text):
        return "hard"
    # Long or highly compound asks lean hard.
    if len(text) > 600:
        return "hard"
    if text.count(".") + text.count(";") + text.count("\n") >= 6:
        return "hard"
    return "easy"


def _smoke() -> int:
    """Smoke-test both tiers against the local endpoint."""
    import asyncio

    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    async def ping(tier: Tier) -> str:
        agent = LlmAgent(
            name=f"smoke_{tier}",
            model=make_llm(tier),
            instruction="Reply with exactly the word PONG and nothing else.",
        )
        runner = InMemoryRunner(agent=agent, app_name="smoke")
        sess = await runner.session_service.create_session(app_name="smoke", user_id="u")
        msg = types.Content(role="user", parts=[types.Part(text="ping")])
        out = ""
        async for ev in runner.run_async(user_id="u", session_id=sess.id, new_message=msg):
            if ev.content and ev.content.parts:
                for p in ev.content.parts:
                    if getattr(p, "text", None):
                        out += p.text
        return out.strip()

    for tier in ("easy", "hard"):
        model_id = settings.model_hard if tier == "hard" else settings.model_easy
        cls = classify_difficulty("design and architect a multi-step plan" if tier == "hard" else "say hi")
        try:
            resp = asyncio.run(ping(tier))  # type: ignore[arg-type]
            print(f"[{tier:4}] model={model_id:20} classify_demo={cls:4} -> {resp!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{tier:4}] model={model_id:20} ERROR: {type(exc).__name__}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    import sys

    if "--smoke" in sys.argv:
        raise SystemExit(_smoke())
    print("core.model: use make_llm(tier) / classify_difficulty(text). Run with --smoke to test.")
