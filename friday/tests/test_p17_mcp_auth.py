"""P17: MCP auth plumbing, credentials API, media extraction, manage tools."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_mcp_env_for_resolves_from_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    monkeypatch.delenv("TEST_MCP_KEY", raising=False)
    from auth import vault
    from control_plane.builder import mcp_env_for

    spec = {"env": {}, "requires": ["TEST_MCP_KEY"]}
    env, missing = mcp_env_for(spec)
    assert missing == ["TEST_MCP_KEY"]

    vault.set_credential("TEST_MCP_KEY", "sk-stored")
    env, missing = mcp_env_for(spec)
    assert missing == []
    assert env["TEST_MCP_KEY"] == "sk-stored"


def test_mcp_auth_status_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    monkeypatch.delenv("NOPE_KEY", raising=False)
    from control_plane.builder import mcp_auth_status

    s = mcp_auth_status({"requires": ["NOPE_KEY"]})
    assert s == {"requires": ["NOPE_KEY"], "missing": ["NOPE_KEY"], "authenticated": False}
    assert mcp_auth_status({})["authenticated"] is True


def test_credentials_api_stores_and_resolves_request(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    from auth import vault
    from control_plane import approvals
    from control_plane.app import app

    entry = approvals.submit(
        "credential",
        summary="provide TEST_API_TOKEN for TestSvc",
        payload={"service": "TestSvc", "key_name": "TEST_API_TOKEN", "instructions": ""},
    )
    client = TestClient(app)
    r = client.post("/api/credentials", json={"key": "TEST_API_TOKEN", "value": "tok-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "tok-123" not in json.dumps(body)  # value never echoed
    assert entry["id"] in body["resolved_requests"]
    assert vault.get_credential("TEST_API_TOKEN") == "tok-123"
    assert approvals.get(entry["id"])["status"] == "applied"
    # names-only listing
    assert "TEST_API_TOKEN" in client.get("/api/credentials").json()["keys"]


def test_extract_media_images_and_html():
    from control_plane.streaming import _extract_media

    resp = {
        "result": json.dumps(
            {
                "content": [
                    {"type": "text", "text": "took a screenshot"},
                    {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
                    {
                        "type": "resource",
                        "resource": {"mimeType": "text/html", "text": "<b>chart</b>"},
                    },
                ]
            }
        )
    }
    media = _extract_media(resp)
    assert media is not None
    assert media["images"] == [{"mime": "image/png", "data": "aGVsbG8="}]
    assert media["html"] == ["<b>chart</b>"]
    # plain text results carry no media
    assert _extract_media({"result": "just text"}) is None
    assert _extract_media({"result": json.dumps({"content": [{"type": "text", "text": "x"}]})}) is None


def test_manage_tools_register_and_attach_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    reg = tmp_path / "registry"
    reg.mkdir()
    (reg / "mcp.json").write_text(json.dumps({"servers": {}}))
    (reg / "agents.json").write_text(
        json.dumps({"agents": {"root": {"tier": "easy", "toolsets": [], "mcp": []}}})
    )
    monkeypatch.setenv("FRIDAY_REGISTRY_DIR", str(reg))

    from control_plane import approvals
    from mcp_tools import manage

    # 1. stage registration (gated — not applied yet)
    out = manage.add_mcp_server(
        "ghub", "npx -y @modelcontextprotocol/server-github", "GitHub", requires="GITHUB_TOKEN"
    )
    assert "staged" in out
    action_id = out.split("request ")[1].split(")")[0]
    assert manage.apply_mcp_change(action_id).startswith("error:")  # blocked pre-approval

    # 2. approve + apply -> registered with auth requirement
    approvals.decide(action_id, approve=True)
    applied = manage.apply_mcp_change(action_id)
    assert "registered" in applied and "GITHUB_TOKEN" in applied
    cfg = json.loads((reg / "mcp.json").read_text())
    assert cfg["servers"]["ghub"]["requires"] == ["GITHUB_TOKEN"]

    # 3. attach flow (gated the same way)
    out = manage.attach_mcp_server("ghub", "root")
    action_id = out.split("request ")[1].split(")")[0]
    approvals.decide(action_id, approve=True)
    assert "attached" in manage.apply_mcp_change(action_id)
    agents = json.loads((reg / "agents.json").read_text())
    assert "ghub" in agents["agents"]["root"]["mcp"]

    # 4. list reflects auth state
    listed = json.loads(manage.list_mcp_servers())
    ghub = next(s for s in listed["servers"] if s["name"] == "ghub")
    assert ghub["authenticated"] is False and ghub["missing_credentials"] == ["GITHUB_TOKEN"]
