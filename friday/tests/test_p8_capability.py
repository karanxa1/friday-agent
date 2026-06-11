"""P8 verification: vault + auth requests + capability self-extension."""

from __future__ import annotations

import importlib
import json
import tempfile

import pytest

from control_plane import builder


@pytest.fixture(autouse=True)
def temp_home(monkeypatch):
    import shutil
    from pathlib import Path

    d = tempfile.mkdtemp(prefix="friday-p8-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    monkeypatch.setenv("FRIDAY_AUTONOMY", "L1")
    # Isolated registry dir so capability tests don't mutate the real mcp.json.
    reg = tempfile.mkdtemp(prefix="friday-p8-reg-")
    real_mcp = Path(__file__).resolve().parent.parent / "registry" / "mcp.json"
    shutil.copy(real_mcp, Path(reg) / "mcp.json")
    monkeypatch.setenv("FRIDAY_REGISTRY_DIR", reg)
    import core.config as cfg

    importlib.reload(cfg)
    import control_plane.approvals as ap
    import auth.vault as v

    importlib.reload(ap)
    importlib.reload(v)
    import auth.tools as at
    import capability.tools as ct

    importlib.reload(at)
    importlib.reload(ct)
    yield d


def test_vault_roundtrip_encrypted():
    import auth.vault as v
    from core.config import settings

    v.set_credential("X_API_KEY", "super-secret-123")
    assert v.get_credential("X_API_KEY") == "super-secret-123"
    assert "X_API_KEY" in v.list_credentials()
    # On-disk file must not contain the plaintext.
    raw = (settings.home / "vault.enc").read_bytes()
    assert b"super-secret-123" not in raw


def test_request_credential_gated():
    import auth.tools as at
    import control_plane.approvals as ap

    out = at.request_credential("X / Twitter", "X_API_KEY", "Get it from developer.x.com")
    assert "requested credential" in out
    pend = ap.pending()
    assert any(p["type"] == "credential" for p in pend)


def test_create_tool_and_apply_hot_loads():
    import capability.tools as ct
    import control_plane.approvals as ap
    from core.registry import registry

    code = "def shout(text: str) -> str:\n    \"\"\"Uppercase text.\"\"\"\n    return text.upper()"
    out = ct.create_tool("shout", "custom", code, description="Uppercase text.")
    assert "staged new tool" in out
    aid = ap.pending()[0]["id"]
    # gated: not approved yet
    assert ct.apply_capability(aid).startswith("error")
    ap.decide(aid, approve=True)
    result = ct.apply_capability(aid)
    assert "created + loaded" in result
    # The new tool is now registered.
    names = {t.name for t in registry.list()}
    assert "shout" in names


def test_create_mcp_server_registers():
    import capability.tools as ct
    import control_plane.approvals as ap
    from core.config import settings

    server_code = (
        "from mcp.server.fastmcp import FastMCP\n"
        "mcp = FastMCP('gen')\n"
        "@mcp.tool()\n"
        "def ping() -> str:\n    return 'pong'\n"
        "if __name__ == '__main__':\n    mcp.run()\n"
    )
    ct.create_mcp_server("genping", server_code, description="test server")
    aid = ap.pending()[0]["id"]
    ap.decide(aid, approve=True)
    result = ct.apply_capability(aid)
    assert "registered in mcp.json" in result
    cfg = json.loads((settings.registry_dir / "mcp.json").read_text())
    assert "genping" in cfg["servers"]
