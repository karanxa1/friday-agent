"""Central configuration for Friday.

Loads from environment (and a .env file if present) and exposes a single
``settings`` object plus helpers for the runtime home directory layout that
mirrors Friday's ``~/.friday`` structure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency).

    Only sets keys that are not already present in the environment so real
    env vars always win over the file.
    """
    # Look for .env next to the project root (parent of this file's package).
    here = Path(__file__).resolve().parent.parent
    env_path = here / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (ValueError, TypeError):
        return default


def _default_model(tier: str) -> str:
    """Default model id for a tier, depending on the active LLM provider.

    For the ``vertex`` provider we run a single Gemini model for both tiers;
    for the (legacy) Anthropic-protocol provider we keep the Claude defaults.
    """
    provider = _env("FRIDAY_LLM_PROVIDER", "anthropic").lower()
    if provider in ("vertex", "gemini"):
        return "gemini-3.5-flash"
    return "claude-opus-4-8" if tier == "hard" else "claude-sonnet-4-6"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings, resolved once at import time."""

    # Provider:
    #   "anthropic" — Anthropic-protocol endpoint (legacy proxy / direct API)
    #   "vertex"    — Google Vertex AI (Gemini) via ADC / service account
    #   "gemini"    — Google Gemini Developer API (AI Studio) via a simple API key
    llm_provider: str = field(default_factory=lambda: _env("FRIDAY_LLM_PROVIDER", "anthropic").lower())
    llm_base_url: str = field(default_factory=lambda: _env("FRIDAY_LLM_BASE_URL", "http://localhost:8990"))
    llm_api_key: str = field(default_factory=lambda: _env("FRIDAY_LLM_API_KEY", ""))
    # Vertex AI settings (used when llm_provider == "vertex"). Gemini 3.5 Flash
    # is served only on the "global" location.
    vertex_project: str = field(default_factory=lambda: _env("FRIDAY_VERTEX_PROJECT", ""))
    vertex_location: str = field(default_factory=lambda: _env("FRIDAY_VERTEX_LOCATION", "global"))
    # Gemini Developer API key (used when llm_provider == "gemini").
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY", ""))
    model_hard: str = field(default_factory=lambda: _env("FRIDAY_MODEL_HARD", _default_model("hard")))
    model_easy: str = field(default_factory=lambda: _env("FRIDAY_MODEL_EASY", _default_model("easy")))
    force_tier: str = field(default_factory=lambda: _env("FRIDAY_FORCE_TIER", ""))
    thinking: bool = field(default_factory=lambda: _env("FRIDAY_THINKING", "1") not in ("0", "false", "False", ""))
    thinking_budget: int = field(default_factory=lambda: _env_int("FRIDAY_THINKING_BUDGET", 2048))
    max_tokens: int = field(default_factory=lambda: _env_int("FRIDAY_MAX_TOKENS", 8192))

    # Context compression: when the running conversation's estimated tokens
    # exceed ``context_limit``, older turns are summarized into a compact note
    # and the most recent ``compact_keep`` tokens are kept verbatim. 0 disables.
    context_limit: int = field(default_factory=lambda: _env_int("FRIDAY_CONTEXT_LIMIT", 120_000))
    compact_keep: int = field(default_factory=lambda: _env_int("FRIDAY_COMPACT_KEEP", 24_000))

    callmissed_api_key: str = field(default_factory=lambda: _env("CALLMISSED_API_KEY", ""))
    callmissed_base_url: str = field(default_factory=lambda: _env("CALLMISSED_BASE_URL", "https://api.callmissed.com"))

    autonomy: str = field(default_factory=lambda: _env("FRIDAY_AUTONOMY", "L1") or "L1")
    max_spawn_depth: int = field(default_factory=lambda: _env_int("FRIDAY_MAX_SPAWN_DEPTH", 3))
    max_fanout: int = field(default_factory=lambda: _env_int("FRIDAY_MAX_FANOUT", 4))
    run_budget_seconds: int = field(default_factory=lambda: _env_int("FRIDAY_RUN_BUDGET_SECONDS", 900))

    # Browser: headed by default so a human can log into sites (Instagram etc.)
    # in the visible window; set FRIDAY_BROWSER_HEADLESS=1 for servers/CI. The
    # session uses a persistent profile so logins survive across runs.
    browser_headless: bool = field(
        default_factory=lambda: _env("FRIDAY_BROWSER_HEADLESS", "0") in ("1", "true", "True")
    )

    @property
    def home(self) -> Path:
        """Runtime home dir (mirrors ~/.friday). Override with FRIDAY_HOME."""
        override = _env("FRIDAY_HOME", "")
        base = Path(override).expanduser() if override else Path.home() / ".friday"
        return base

    def ensure_home(self) -> Path:
        """Create the runtime home layout if missing and return its path."""
        base = self.home
        for sub in ("skills", "skills/.archive", "memories", "logs", "logs/curator", "sandboxes/docker"):
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    # --- derived paths ---
    @property
    def file_root(self) -> Path:
        """Root the `files` toolset may read/edit.

        Default: the agent's sandboxed workspace (``~/.friday/workspace``).
        Operators can widen this with FRIDAY_FILE_ROOT:
          - ``workspace`` (default) — sandboxed scratch area
          - ``project``   — the Friday project tree (read/edit its own repo)
          - ``home``      — the user's home directory
          - any absolute path
        Path-traversal guards always confine access to within this root.
        """
        choice = _env("FRIDAY_FILE_ROOT", "").strip()
        if not choice or choice == "workspace":
            return self.home / "workspace"
        if choice == "project":
            return Path(__file__).resolve().parent.parent
        if choice == "home":
            return Path.home()
        return Path(choice).expanduser()

    @property
    def skills_dir(self) -> Path:
        return self.home / "skills"

    @property
    def archive_dir(self) -> Path:
        return self.home / "skills" / ".archive"

    @property
    def memories_dir(self) -> Path:
        return self.home / "memories"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    @property
    def sessions_db(self) -> Path:
        return self.home / "sessions.db"

    @property
    def browser_profile_dir(self) -> Path:
        """Persistent Chromium profile so browser logins survive across runs."""
        return self.home / "browser_profile"

    @property
    def registry_dir(self) -> Path:
        # Registry lives inside the project tree so it is git-tracked & self-editable.
        # Override with FRIDAY_REGISTRY_DIR (tests).
        override = _env("FRIDAY_REGISTRY_DIR", "")
        if override:
            return Path(override).expanduser()
        return Path(__file__).resolve().parent.parent / "registry"


settings = Settings()
