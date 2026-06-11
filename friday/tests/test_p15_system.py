"""P15: system toolset — run_command, glob_files, grep_files (confined to root)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path / "friday-home"))
    yield


def test_run_command_basic():
    from friday_tools.system import run_command

    out = run_command("echo hello-friday")
    assert "exit code: 0" in out
    assert "hello-friday" in out


def test_run_command_nonzero_exit():
    from friday_tools.system import run_command

    out = run_command("exit 3")
    assert "exit code: 3" in out


def test_run_command_timeout():
    from friday_tools.system import run_command

    out = run_command("sleep 5", timeout=1)
    assert "timed out" in out


def test_run_command_cwd_escape_blocked():
    from friday_tools.system import run_command

    assert "escapes" in run_command("ls", cwd="../..")
    assert "escapes" in run_command("ls", cwd="/etc")


def test_run_command_empty():
    from friday_tools.system import run_command

    assert "empty command" in run_command("   ")


def test_run_command_runs_in_file_root():
    from friday_tools.system import run_command
    from friday_tools.files import write_file

    write_file("marker.txt", "x")
    out = run_command("ls")
    assert "marker.txt" in out


def test_glob_files():
    from friday_tools.system import glob_files
    from friday_tools.files import write_file

    write_file("a.py", "print(1)\n")
    write_file("pkg/b.py", "print(2)\n")
    write_file("pkg/c.txt", "nope\n")
    out = glob_files("**/*.py")
    assert "a.py" in out
    assert "pkg/b.py" in out
    assert "c.txt" not in out


def test_glob_no_match():
    from friday_tools.system import glob_files

    assert "no files match" in glob_files("**/*.nonexistent")


def test_glob_escape_blocked():
    from friday_tools.system import glob_files

    assert "escapes" in glob_files("*", path="../..")


def test_grep_files():
    from friday_tools.system import grep_files
    from friday_tools.files import write_file

    write_file("doc.md", "the quick brown fox\njumps over\n")
    write_file("other.md", "nothing here\n")
    out = grep_files("brown")
    assert "doc.md:1:" in out
    assert "brown fox" in out


def test_grep_include_filter():
    from friday_tools.system import grep_files
    from friday_tools.files import write_file

    write_file("keep.py", "target = 1\n")
    write_file("skip.txt", "target here\n")
    out = grep_files("target", include="*.py")
    assert "keep.py" in out
    assert "skip.txt" not in out


def test_grep_no_match():
    from friday_tools.system import grep_files
    from friday_tools.files import write_file

    write_file("x.txt", "abc\n")
    assert "no matches" in grep_files("zzz-not-there")


def test_grep_invalid_regex():
    from friday_tools.system import grep_files

    assert "invalid regex" in grep_files("(unclosed")


def test_grep_escape_blocked():
    from friday_tools.system import grep_files

    assert "escapes" in grep_files("x", path="../..")


def test_system_toolset_registered():
    from control_plane import builder
    from core.builtin_tools import list_all_tools

    builder.import_tool_modules()
    out = list_all_tools()
    assert "[system]" in out


def test_root_agent_resolves_system_tools():
    from control_plane import builder
    from core.registry import registry

    builder.import_tool_modules()
    spec = builder.load_registry("agents.json")["agents"]["root"]
    assert "system" in spec["toolsets"]
    funcs = registry.resolve(spec["toolsets"])
    names = {f.__name__ for f in funcs}
    for expected in ("run_command", "glob_files", "grep_files"):
        assert expected in names, f"{expected} not resolved for root agent"
