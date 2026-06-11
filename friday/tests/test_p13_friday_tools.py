"""P13: ported worker tools — files, web (guards), todo, recall, discovery."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path / "friday-home"))
    # settings reads env lazily via properties for home; modules cache nothing.
    yield


def test_workspace_file_roundtrip():
    from friday_tools.files import delete_file, edit_file, list_files, read_file, write_file

    assert "wrote" in write_file("notes/plan.md", "# Plan\nstep one\n")
    assert "step one" in read_file("notes/plan.md")
    assert "edited" in edit_file("notes/plan.md", "step one", "step two")
    assert "step two" in read_file("notes/plan.md")
    listing = list_files("notes")
    assert "plan.md" in listing
    assert "deleted" in delete_file("notes/plan.md")
    assert "not found" in read_file("notes/plan.md")


def test_workspace_path_escape_blocked():
    from friday_tools.files import read_file, write_file

    assert "escapes" in write_file("../outside.txt", "nope")
    assert "escapes" in read_file("../../etc/passwd")
    assert "escapes" in read_file("/etc/passwd")


def test_symlink_escape_blocked(tmp_path):
    """A symlink inside the root that points outside it must not be followed."""
    from core.config import settings
    from friday_tools.files import read_file, write_file

    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    root = settings.file_root
    root.mkdir(parents=True, exist_ok=True)
    link = root / "escape"
    try:
        link.symlink_to(tmp_path)
    except OSError:
        return  # symlinks unsupported on this platform
    # Reading through the symlink must be refused, not leak the secret.
    out = read_file("escape/secret.txt")
    assert "top secret" not in out
    assert out.startswith("error")
    assert "top secret" not in write_file("escape/secret.txt", "overwrite")


def test_fetch_url_guards():
    from friday_tools.web import fetch_url

    assert "only http/https" in fetch_url("file:///etc/passwd")
    assert "private/loopback" in fetch_url("http://127.0.0.1:8080/")
    assert "private/loopback" in fetch_url("http://localhost/")


def test_redirect_to_private_host_blocked():
    """A public host must not be able to redirect us into localhost (SSRF)."""
    import httpx

    from friday_tools.web import _send_guarded

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8080/admin"})
        raise AssertionError("private hop must never be requested")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp, err = _send_guarded(client, "GET", "http://example.com/start")
    assert resp is None
    assert err is not None and "private/loopback" in err


def test_redirect_chain_capped():
    import httpx

    from friday_tools.web import _send_guarded

    def handler(request: httpx.Request) -> httpx.Response:
        n = int(request.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"http://example.com/{n + 1}"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp, err = _send_guarded(client, "GET", "http://example.com/0")
    assert resp is None
    assert err is not None and "redirects" in err


def test_download_filename_guard():
    from friday_tools.web import download_file

    assert "plain name" in download_file("https://example.com/a.txt", "../evil.txt")
    assert "plain name" in download_file("https://example.com/a.txt", ".hidden")


def test_todo_lifecycle():
    from friday_tools.todo import todo_add, todo_clear, todo_done, todo_list

    assert "#1" in todo_add("write report")
    assert "#2" in todo_add("ship it")
    listing = todo_list()
    assert "[ ] #1 write report" in listing
    assert "completed" in todo_done(1)
    assert "[x] #1" in todo_list()
    assert "not found" in todo_done(99)
    assert "removed 1" in todo_clear()
    assert "#2 ship it" in todo_list()


def test_recall_search_and_activity():
    from core.config import settings
    from friday_tools.files import write_file
    from friday_tools.recall import recall_search, recent_activity

    settings.ensure_home()
    (settings.memories_dir / "MEMORY.md").write_text("Friday prefers tabs\n", encoding="utf-8")
    write_file("doc.md", "the launch is on friday prefers nothing\n")
    out = recall_search("prefers")
    assert "memory/MEMORY.md" in out
    assert "workspace/doc.md" in out
    assert "(no matches" in recall_search("zzz-not-there")
    assert "files.write" in recent_activity(limit=50, prefix="files.")


def test_list_all_tools_discovery():
    from control_plane import builder

    builder.import_tool_modules()
    from core.builtin_tools import list_all_tools

    out = list_all_tools()
    for ts in ("[files]", "[web]", "[todo]", "[recall]"):
        assert ts in out, f"missing toolset {ts}"
    filtered = list_all_tools("todo")
    assert "todo_add" in filtered and "fetch_url" not in filtered


def test_root_agent_resolves_new_toolsets():
    from control_plane import builder
    from core.registry import registry

    builder.import_tool_modules()
    spec = builder.load_registry("agents.json")["agents"]["root"]
    funcs = registry.resolve(spec["toolsets"])
    names = {f.__name__ for f in funcs}
    for expected in ("write_file", "fetch_url", "todo_add", "recall_search", "list_all_tools"):
        assert expected in names, f"{expected} not resolved for root agent"
