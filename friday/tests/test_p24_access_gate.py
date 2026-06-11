"""P24: whole-app access password gate.

When FRIDAY_ACCESS_PASSWORD is set, every /api route (except the login/auth/
health endpoints) requires an access cookie issued by POST /api/login. Empty
password keeps the API open (local dev).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gated(monkeypatch):
    """App with the password gate active and a non-Secure cookie (so the http
    TestClient resends it — in prod the cookie is Secure over HTTPS)."""
    from control_plane import app as appmod
    from core.config import settings

    monkeypatch.setattr(appmod, "_ACCESS_PASSWORD", "APAC")
    old = settings.public_url
    object.__setattr__(settings, "public_url", "")  # -> cookie not Secure-only
    try:
        yield TestClient(appmod.app)
    finally:
        object.__setattr__(settings, "public_url", old)


def test_protected_routes_require_login(gated):
    assert gated.get("/api/config").status_code == 401
    assert gated.get("/api/auth").json() == {"authed": False, "required": True}
    # login/auth/health are exempt so the gate is reachable.
    assert gated.get("/api/health").status_code == 200


def test_wrong_password_rejected(gated):
    assert gated.post("/api/login", json={"password": "nope"}).status_code == 401
    assert gated.get("/api/config").status_code == 401


def test_login_then_access_then_logout(gated):
    assert gated.post("/api/login", json={"password": "APAC"}).status_code == 200
    assert gated.get("/api/config").status_code == 200  # cookie now carried
    assert gated.get("/api/auth").json()["authed"] is True
    # artifacts mount is gated too (404 = authed but missing, not 401 = locked)
    assert gated.get("/api/files/none.png").status_code == 404
    gated.post("/api/logout")
    assert gated.get("/api/config").status_code == 401


def test_gate_open_when_no_password(monkeypatch):
    from control_plane import app as appmod

    monkeypatch.setattr(appmod, "_ACCESS_PASSWORD", "")
    c = TestClient(appmod.app)
    assert c.get("/api/auth").json() == {"authed": True, "required": False}
    assert c.post("/api/login", json={"password": "anything"}).json()["required"] is False
    assert c.get("/api/config").status_code == 200
