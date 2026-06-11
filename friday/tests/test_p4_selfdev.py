"""P4 verification: self-dev toolset (read/write/edit/validate/apply, gated, git-backed)."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from control_plane import builder

_PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def temp_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="friday-p4-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    monkeypatch.setenv("FRIDAY_AUTONOMY", "L1")

    # Isolated self-dev root: a temp git repo with a copy of pyproject.toml
    # so read_self finds it, and git_snapshot never touches the real repo.
    selfdev = tempfile.mkdtemp(prefix="friday-selfdev-")
    shutil.copy(_PROJECT / "pyproject.toml", Path(selfdev) / "pyproject.toml")
    (Path(selfdev) / "data").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=selfdev)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=selfdev)
    subprocess.run(["git", "config", "user.name", "t"], cwd=selfdev)
    monkeypatch.setenv("FRIDAY_SELFDEV_ROOT", selfdev)
    monkeypatch.setenv("FRIDAY_SELFDEV_GIT_ROOT", selfdev)

    import core.config as cfg

    importlib.reload(cfg)
    import control_plane.approvals as ap

    importlib.reload(ap)
    yield d
    shutil.rmtree(selfdev, ignore_errors=True)


def test_read_self_reads_project_file():
    import self_dev.tools as sd

    content = sd.read_self("pyproject.toml")
    assert "friday" in content


def test_read_self_rejects_escape():
    import self_dev.tools as sd

    out = sd.read_self("../../etc/passwd")
    assert out.startswith("error")


def test_write_self_stages_and_requires_approval():
    import self_dev.tools as sd
    import control_plane.approvals as ap

    out = sd.write_self("data/_selftest.txt", "hello self-edit")
    assert "staged self-edit" in out
    pend = ap.pending()
    assert len(pend) == 1
    assert pend[0]["type"] == "self_edit"

    # apply before approval -> refused
    aid = pend[0]["id"]
    assert sd.apply_pending(aid).startswith("error")

    # approve then apply
    ap.decide(aid, approve=True)
    result = sd.apply_pending(aid)
    assert "applied" in result
    # file now exists
    assert sd.read_self("data/_selftest.txt") == "hello self-edit"


def test_validate_self_detects_syntax_error():
    import self_dev.tools as sd
    import control_plane.approvals as ap

    bad = "def broken(:\n    pass\n"
    out = sd.write_self("data/_bad.py", bad)
    aid = ap.pending()[0]["id"]
    ap.decide(aid, approve=True)
    sd.apply_pending(aid)
    assert sd.validate_self("data/_bad.py").startswith("SYNTAX ERROR")


def test_registered_in_self_dev_toolset():
    from core.registry import registry

    builder.import_tool_modules()
    names = {t.name for t in registry.list() if t.toolset == "self_dev"}
    assert {"read_self", "write_self", "edit_self", "apply_pending", "reload_module"} <= names
