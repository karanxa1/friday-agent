"""P10 verification: control-plane FastAPI app boots and endpoints respond."""

from __future__ import annotations

import importlib
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    d = tempfile.mkdtemp(prefix="friday-p10-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    monkeypatch.setenv("FRIDAY_AUTONOMY", "L1")
    import core.config as cfg

    importlib.reload(cfg)
    import control_plane.approvals as ap

    importlib.reload(ap)
    import control_plane.app as appmod

    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["service"] == "friday"


def test_dashboard_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "Friday" in r.text


def test_approvals_empty(client):
    r = client.get("/api/approvals")
    assert r.status_code == 200
    assert r.json()["pending"] == []


def test_approval_flow_via_api(client):
    # Stage a publish via the social tools, then approve through the API.
    import domains.social_media.tools as t

    importlib.reload(t)
    t.queue_post("x", "hello from a test")
    pend = client.get("/api/approvals").json()["pending"]
    assert len(pend) == 1
    aid = pend[0]["id"]
    r = client.post(f"/api/approvals/{aid}", json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "approved"


def test_audit_endpoint(client):
    r = client.get("/api/audit?limit=10")
    assert r.status_code == 200 and "events" in r.json()


def test_skills_endpoint(client):
    r = client.get("/api/skills")
    assert r.status_code == 200 and "skills" in r.json()
