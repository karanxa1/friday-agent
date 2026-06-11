"""P16: ported file ops — paginated read, lint-on-write, fuzzy patch, search."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path / "friday-home"))
    yield


# --- read_file: pagination + line numbers ----------------------------------

def test_read_file_line_numbers():
    from friday_tools.files import read_file, write_file

    write_file("a.txt", "one\ntwo\nthree\n")
    out = read_file("a.txt")
    assert "1| one" in out
    assert "2| two" in out
    assert "3| three" in out


def test_read_file_pagination():
    from friday_tools.files import read_file, write_file

    write_file("big.txt", "\n".join(f"line{i}" for i in range(1, 101)) + "\n")
    out = read_file("big.txt", offset=10, limit=3)
    assert "10| line10" in out
    assert "12| line12" in out
    assert "line13" not in out
    assert "showing lines 10-12 of 100" in out


def test_read_file_binary_guard():
    from friday_tools.files import read_file
    from core.config import settings

    settings.file_root.mkdir(parents=True, exist_ok=True)
    (settings.file_root / "img.png").write_bytes(b"\x89PNG\r\n")
    out = read_file("img.png")
    assert "binary" in out.lower()


def test_read_file_suggests_similar():
    from friday_tools.files import read_file, write_file

    write_file("config.yaml", "k: v\n")
    out = read_file("confnig.yaml")  # typo
    assert "not found" in out
    assert "config.yaml" in out  # did-you-mean suggestion


# --- write_file: lint-on-write ---------------------------------------------

def test_write_file_lint_new_error():
    from friday_tools.files import write_file

    out = write_file("bad.py", "def f(:\n")  # syntax error
    assert "wrote" in out
    assert "syntax error" in out.lower()


def test_write_file_clean_python_no_warning():
    from friday_tools.files import write_file

    out = write_file("good.py", "def f():\n    return 1\n")
    assert "wrote" in out
    assert "syntax error" not in out.lower()


def test_write_file_preexisting_error_not_flagged():
    from friday_tools.files import write_file

    write_file("x.py", "def broken(:\n")  # already broken (warns once)
    # Overwrite, still broken but pre-existing relative to this write's "old"
    out = write_file("x.py", "def still_broken(:\n")
    # old content was already invalid, so no NEW error is attributed
    assert "wrote" in out
    assert "syntax error" not in out.lower()


def test_write_file_json_lint():
    from friday_tools.files import write_file

    assert "syntax error" in write_file("c.json", "{bad json}").lower()
    assert "syntax error" not in write_file("d.json", '{"ok": true}').lower()


# --- patch: fuzzy matching + unified diff ----------------------------------

def test_patch_exact_with_diff():
    from friday_tools.files import patch, write_file

    write_file("p.py", "x = 1\ny = 2\n")
    out = patch("p.py", "x = 1", "x = 99")
    assert "1 replacement" in out
    assert "via exact" in out
    assert "-x = 1" in out
    assert "+x = 99" in out


def test_patch_fuzzy_whitespace():
    from friday_tools.files import patch, read_file, write_file

    write_file("q.py", "def f():\n        return  1\n")
    # old_string has different indentation/spacing than the file
    out = patch("q.py", "def f():\n    return 1", "def f():\n    return 2")
    assert "replacement" in out
    assert "2" in read_file("q.py")


def test_patch_ambiguous_requires_unique():
    from friday_tools.files import patch, write_file

    write_file("dup.txt", "foo\nfoo\nfoo\n")
    out = patch("dup.txt", "foo", "bar")
    assert "error" in out
    assert "matches" in out.lower()


def test_patch_replace_all():
    from friday_tools.files import patch, read_file, write_file

    write_file("dup2.txt", "foo\nfoo\nfoo\n")
    out = patch("dup2.txt", "foo", "bar", replace_all=True)
    assert "3 replacement" in out
    assert "foo" not in read_file("dup2.txt")


def test_patch_no_match_did_you_mean():
    from friday_tools.files import patch, write_file

    write_file("r.py", "alpha = 1\nbeta = 2\n")
    out = patch("r.py", "completely_unrelated_token_xyz = 999", "alpha = 9")
    assert "error" in out


def test_patch_not_found_suggests_filename():
    from friday_tools.files import patch, write_file

    write_file("real.py", "a=1\n")
    out = patch("realx.py", "a=1", "a=2")
    assert "not found" in out


# --- search_files: content/files/output modes ------------------------------

def test_search_content_mode():
    from friday_tools.files import search_files, write_file

    write_file("s1.py", "import os\nx = 1\n")
    write_file("s2.py", "y = 2\n")
    out = search_files("import", target="content")
    assert "s1.py:1:" in out
    assert "s2.py" not in out


def test_search_files_mode():
    from friday_tools.files import search_files, write_file

    write_file("mod/a.py", "1\n")
    write_file("mod/b.txt", "2\n")
    out = search_files("*.py", target="files")
    assert "mod/a.py" in out
    assert "b.txt" not in out


def test_search_files_only_output_mode():
    from friday_tools.files import search_files, write_file

    write_file("f1.py", "TODO fix\n")
    write_file("f2.py", "nothing\n")
    out = search_files("TODO", target="content", output_mode="files_only")
    assert "f1.py" in out
    assert "f2.py" not in out


def test_search_count_output_mode():
    from friday_tools.files import search_files, write_file

    write_file("c.py", "a\na\na\n")
    out = search_files("a", target="content", output_mode="count")
    assert "c.py" in out
    assert "3" in out


def test_search_context_lines():
    from friday_tools.files import search_files, write_file

    write_file("ctx.py", "before\nMATCH\nafter\n")
    out = search_files("MATCH", target="content", context=1)
    assert "before" in out
    assert "after" in out


def test_search_file_glob_filter():
    from friday_tools.files import search_files, write_file

    write_file("g.py", "needle\n")
    write_file("g.txt", "needle\n")
    out = search_files("needle", target="content", file_glob="*.py")
    assert "g.py" in out
    assert "g.txt" not in out


def test_search_invalid_regex():
    from friday_tools.files import search_files

    assert "invalid regex" in search_files("(unclosed", target="content")


def test_search_escape_blocked():
    from friday_tools.files import search_files

    assert "escapes" in search_files("x", target="content", path="../..")


# --- backward compat: existing files-toolset tools still work --------------

def test_backward_compat_roundtrip():
    from friday_tools.files import delete_file, edit_file, list_files, read_file, write_file

    assert "wrote" in write_file("notes/plan.md", "step one\n")
    assert "step one" in read_file("notes/plan.md")
    assert "edited" in edit_file("notes/plan.md", "step one", "step two")
    assert "step two" in read_file("notes/plan.md")
    assert "plan.md" in list_files("notes")
    assert "deleted" in delete_file("notes/plan.md")


def test_new_file_tools_registered():
    from control_plane import builder
    from core.registry import registry

    builder.import_tool_modules()
    spec = builder.load_registry("agents.json")["agents"]["root"]
    funcs = registry.resolve(spec["toolsets"])
    names = {f.__name__ for f in funcs}
    for expected in ("read_file", "write_file", "patch", "search_files", "list_files"):
        assert expected in names, f"{expected} not resolved for root agent"
