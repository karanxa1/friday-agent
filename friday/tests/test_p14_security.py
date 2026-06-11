"""P14: security hardening regressions (CORS, token auth, env scrub, gates)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def _fresh_app(monkeypatch, **env):
    """Reimport the app module so middleware picks up env (token/CORS)."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import control_plane.app as appmod

    appmod = importlib.reload(appmod)
    return appmod.app


def test_cors_not_wildcard():
    from control_plane import app as appmod

    # Default origins are an explicit localhost allowlist, never "*".
    assert "*" not in appmod._CORS_ORIGINS
    assert any("localhost" in o for o in appmod._CORS_ORIGINS)


def test_health_open_without_token():
    from control_plane.app import app

    client = TestClient(app)
    assert client.get("/api/health").status_code == 200


def test_token_auth_blocks_and_allows(monkeypatch):
    app = _fresh_app(monkeypatch, FRIDAY_API_TOKEN="s3cret")
    try:
        client = TestClient(app)
        # health stays open
        assert client.get("/api/health").status_code == 200
        # protected route requires the token
        assert client.get("/api/audit").status_code == 401
        assert client.get("/api/audit", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.get("/api/audit", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
    finally:
        # restore the unauthenticated default app for other tests
        monkeypatch.delenv("FRIDAY_API_TOKEN", raising=False)
        importlib.reload(importlib.import_module("control_plane.app"))


def test_mcp_test_env_is_scrubbed(monkeypatch):
    """The MCP test path must not leak host secrets into the child env."""
    monkeypatch.setenv("FRIDAY_LLM_API_KEY", "sk-should-not-leak")
    from sandbox.docker_env import _scrubbed_env

    env = _scrubbed_env()
    assert "FRIDAY_LLM_API_KEY" not in env
    assert all("KEY" not in k.upper() and "SECRET" not in k.upper() for k in env)
    assert "PATH" in env


def test_l2_whitelist_entries_are_real_action_types():
    from control_plane import approvals

    # Any auto-approve entry must be a real, submitted action type.
    assert approvals._L2_WHITELIST <= approvals.ACTION_TYPES


def test_l2_does_not_auto_approve_self_edit(monkeypatch):
    from control_plane import approvals
    from core.config import settings

    object.__setattr__(settings, "autonomy", "L2")
    try:
        assert approvals.gate("self_edit") is False
        assert approvals.gate("capability") is False
    finally:
        object.__setattr__(settings, "autonomy", "L1")


def test_l3_full_auto_approves_everything(monkeypatch):
    # L3 is the explicit full-autonomy opt-in: every action auto-proceeds.
    from control_plane import approvals
    from core.config import settings

    object.__setattr__(settings, "autonomy", "L3")
    try:
        assert approvals.gate("self_edit") is True
        assert approvals.gate("capability") is True
        assert approvals.gate("credential") is True
    finally:
        object.__setattr__(settings, "autonomy", "L1")


def test_web_url_log_strips_query():
    from friday_tools.web import _log_url

    assert _log_url("https://api.example.com/v1?api_key=SECRET&x=1") == "https://api.example.com/v1?…"
    assert _log_url("https://example.com/page") == "https://example.com/page"
