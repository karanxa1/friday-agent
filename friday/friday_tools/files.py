"""File tools (ported + extended from the reference ``tools/file_tools.py``).

Paths are confined to ``settings.file_root`` — by default the agent's sandboxed
workspace (``~/.friday/workspace``), but operators can widen it to the project
tree or home via ``FRIDAY_FILE_ROOT`` (see core/config.py). Editing Friday's own
code through the approval queue still lives in the ``self_dev`` toolset.

The traversal guard resolves both the root and the target with symlinks
followed (``Path.resolve``), so a symlink inside the root cannot point outside
it.

This toolset mirrors the four the reference agent file tools:
  * ``read_file``    — paginated, line-numbered read with binary guard and
                       "did you mean?" filename suggestions
  * ``write_file``   — full-file write with lint-on-write (only NEW errors)
  * ``patch``        — fuzzy find/replace (9 strategies) returning a unified
                       diff, with replace_all and uniqueness enforcement
  * ``search_files`` — content/files search with output modes + context lines
plus ``list_files`` / ``edit_file`` / ``delete_file`` for convenience.
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool
from friday_tools.fuzzy_match import find_closest_lines, fuzzy_find_and_replace
from friday_tools.lint import has_binary_extension, new_errors_only

_MAX_READ = 50_000
_MAX_WRITE = 200_000
_DEFAULT_LIMIT = 500
_MAX_LIMIT = 2000
_MAX_LINE_LEN = 2000
_SEARCH_DEFAULT_LIMIT = 50


def _root() -> Path:
    root = settings.file_root
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(rel: str) -> Path | None:
    """Resolve ``rel`` inside the file root; None if it escapes.

    Resolves with symlinks followed so neither the path nor any symlink within
    it can escape the root (the reference ``path_security``). The parent is resolved
    for not-yet-existing targets (create/write).
    """
    if os.path.isabs(rel):
        return None
    root = _root().resolve()
    candidate = root / rel
    try:
        target = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    anchor = target if target.exists() else target.parent
    try:
        anchor = anchor.resolve()
    except (OSError, RuntimeError):
        return None
    if target != root and root != anchor and root not in anchor.parents and root not in target.parents:
        return None
    return target


def _suggest_similar(path: str) -> str:
    """Suggest existing files with a similar name (the reference "did you mean?")."""
    target = _safe_path(path)
    if target is None:
        return ""
    parent = target.parent
    if not parent.is_dir():
        return ""
    name = target.name
    try:
        names = [p.name for p in parent.iterdir() if p.is_file()]
    except OSError:
        return ""
    close = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
    if not close:
        return ""
    return " Did you mean: " + ", ".join(close) + "?"


@tool("files", description="List files and directories in the agent's file area.")
def list_files(path: str = ".") -> str:
    """List the contents of a workspace directory.

    Args:
        path: directory relative to the workspace root (default: root).
    """
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if not target.exists():
        return f"error: {path!r} does not exist"
    if target.is_file():
        return f"{path} (file, {target.stat().st_size} bytes)"
    rows = []
    for child in sorted(target.iterdir())[:200]:
        kind = "dir " if child.is_dir() else "file"
        size = "" if child.is_dir() else f" ({child.stat().st_size} bytes)"
        rows.append(f"{kind}  {child.relative_to(_root())}{size}")
    return "\n".join(rows) if rows else "(empty directory)"


@tool(
    "files",
    description="Read a text file with line numbers and pagination (offset/limit). Use instead of cat/head/tail.",
)
def read_file(path: str = "", offset: int = 1, limit: int = _DEFAULT_LIMIT, max_chars: int = _MAX_READ) -> str:
    """Read a workspace file as text, with 'LINE| CONTENT' line numbers.

    Args:
        path: file path relative to the workspace root.
        offset: 1-indexed line number to start reading from (default 1).
        limit: maximum number of lines to read (default 500, max 2000).
        max_chars: hard cap on returned characters.
    """
    if not path:
        return "error: read_file requires a 'path' argument."
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if has_binary_extension(str(target)):
        return (
            f"error: cannot read binary file {path!r} ({target.suffix.lower()}). "
            "Use the vision tools for images, or run_command to inspect binaries."
        )
    if not target.is_file():
        return f"error: {path!r} not found." + _suggest_similar(path)
    try:
        offset = max(1, int(offset))
    except (TypeError, ValueError):
        offset = 1
    try:
        limit = max(1, min(int(limit), _MAX_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"error: {exc}"
    lines = raw.splitlines()
    total = len(lines)
    start = offset - 1
    window = lines[start : start + limit]
    if not window and start >= total and total:
        return f"error: offset {offset} is past end of file ({total} lines)"
    rendered = []
    for i, line in enumerate(window, start=offset):
        if len(line) > _MAX_LINE_LEN:
            line = line[:_MAX_LINE_LEN] + "… (line truncated)"
        rendered.append(f"{i}| {line}")
    out = "\n".join(rendered)
    if len(out) > max_chars:
        out = out[:max_chars] + f"\n… (truncated, {len(out)} chars; narrow with offset/limit)"
    end = min(start + limit, total)
    if end < total or offset > 1:
        out += f"\n(showing lines {offset}-{end} of {total})"
    return out or "(empty file)"


@tool(
    "files",
    description="Write (create or overwrite) a text file. Runs a syntax check and reports only NEW errors.",
)
def write_file(path: str = "", content: str | None = None) -> str:
    """Write ``content`` to a workspace file, creating parent dirs as needed.

    Args:
        path: file path relative to the workspace root.
        content: full text content to write.
    """
    if not path:
        return (
            "error: write_file requires a 'path' argument. Re-call with both "
            "'path' and 'content' set."
        )
    if content is None:
        return (
            "error: write_file requires a 'content' argument (the full text to "
            "write). This is usually a dropped-arg under context pressure — "
            "re-call write_file with both 'path' and the complete 'content'."
        )
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if len(content) > _MAX_WRITE:
        return f"error: content exceeds {_MAX_WRITE} chars"
    old = None
    if target.is_file():
        try:
            old = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            old = None
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)
    audit.log("files.write", path=path, bytes=len(content))
    lint = new_errors_only(target.suffix, old, content)
    msg = f"wrote {len(content)} chars to {path}"
    if lint:
        msg += f"\nwarning: this write introduced a syntax error: {lint}"
    return msg


@tool("files", description="Edit a file via find-and-replace (fuzzy, whitespace tolerant).")
def edit_file(path: str = "", old: str | None = None, new: str | None = None) -> str:
    """Replace ``old`` with ``new`` in a workspace file (single occurrence).

    Args:
        path: file path relative to the workspace root.
        old: text to find (exact, or fuzzy fallback).
        new: replacement text.
    """
    if not path or old is None or new is None:
        return "error: edit_file requires 'path', 'old', and 'new' arguments."
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if not target.is_file():
        return f"error: {path!r} not found"
    text = target.read_text(encoding="utf-8", errors="replace")
    patched, count, strategy, err = fuzzy_find_and_replace(text, old, new, replace_all=False)
    if err:
        hint = find_closest_lines(old, text) if count == 0 else ""
        suffix = f"\nDid you mean:\n{hint}" if hint else ""
        return f"error: {err}{suffix}"
    target.write_text(patched, encoding="utf-8")
    audit.log("files.edit", path=path, strategy=strategy)
    return f"edited {path} (matched via {strategy})"


@tool(
    "files",
    description=(
        "Targeted find-and-replace with fuzzy matching (9 strategies); returns a unified diff. "
        "Use instead of sed/awk. Pass replace_all=true to replace every occurrence."
    ),
)
def patch(path: str = "", old_string: str | None = None, new_string: str | None = None, replace_all: bool = False) -> str:
    """Apply a fuzzy find/replace edit and return a unified diff.

    Args:
        path: file path relative to the workspace root.
        old_string: text to find. Must be unique unless replace_all=true.
        new_string: replacement text (empty string deletes the match).
        replace_all: replace all occurrences instead of requiring uniqueness.
    """
    if not path:
        return "error: patch requires a 'path' argument."
    if old_string is None or new_string is None:
        return (
            "error: patch requires 'old_string' and 'new_string'. If you meant "
            "to create or overwrite the whole file, use write_file instead."
        )
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if not target.is_file():
        return f"error: {path!r} not found." + _suggest_similar(path)
    text = target.read_text(encoding="utf-8", errors="replace")
    patched, count, strategy, err = fuzzy_find_and_replace(text, old_string, new_string, replace_all)
    if err:
        hint = find_closest_lines(old_string, text) if count == 0 else ""
        suffix = f"\nDid you mean one of these sections?\n{hint}" if hint else ""
        return f"error: {err}{suffix}"
    if len(patched) > _MAX_WRITE:
        return f"error: result exceeds {_MAX_WRITE} chars"
    target.write_text(patched, encoding="utf-8")
    audit.log("files.patch", path=path, strategy=strategy, count=count)
    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    lint = new_errors_only(target.suffix, text, patched)
    header = f"patched {path}: {count} replacement(s) via {strategy}\n"
    body = diff or "(no textual diff)"
    if lint:
        body += f"\nwarning: this patch introduced a syntax error: {lint}"
    return header + body


@tool("files", description="Delete a file from the agent's file area.")
def delete_file(path: str = "") -> str:
    """Delete a single workspace file (directories are refused).

    Args:
        path: file path relative to the workspace root.
    """
    if not path:
        return "error: delete_file requires a 'path' argument."
    target = _safe_path(path)
    if target is None:
        return f"error: path {path!r} escapes the workspace"
    if not target.is_file():
        return f"error: {path!r} is not a file"
    target.unlink()
    audit.log("files.delete", path=path)
    return f"deleted {path}"


@tool(
    "files",
    description=(
        "Search file contents (regex) or find files by glob. Use instead of grep/find/ls. "
        "target='content' searches inside files; target='files' lists matching filenames."
    ),
)
def search_files(
    pattern: str = "",
    target: str = "content",
    path: str = ".",
    file_glob: str = "*",
    limit: int = _SEARCH_DEFAULT_LIMIT,
    offset: int = 0,
    output_mode: str = "content",
    context: int = 0,
) -> str:
    """Search the workspace.

    Args:
        pattern: regex (content mode) or glob (files mode, e.g. '*.py').
        target: 'content' to search inside files, 'files' to find by name.
        path: directory to search from, relative to the workspace root.
        file_glob: in content mode, only search files matching this glob.
        limit: max results (default 50).
        offset: skip the first N results (pagination).
        output_mode: content mode only — 'content', 'files_only', or 'count'.
        context: content mode only — lines of context around each match.
    """
    if not pattern:
        return "error: search_files requires a 'pattern' argument."
    base = _safe_path(path or ".")
    if base is None:
        return f"error: path {path!r} escapes the workspace"
    if not base.is_dir():
        if base.is_file():
            base_files = [base]
        else:
            return f"error: {path!r} is not a directory"
    else:
        base_files = None
    root = _root().resolve()
    try:
        limit = max(1, int(limit))
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        limit, offset = _SEARCH_DEFAULT_LIMIT, 0

    # --- files mode: glob by name -----------------------------------------
    if target == "files":
        try:
            found = []
            for p in (base_files or base.rglob(pattern)):
                if not p.is_file():
                    continue
                try:
                    if p.resolve() != root and root not in p.resolve().parents:
                        continue
                    found.append((p.stat().st_mtime, str(p.relative_to(root))))
                except (OSError, RuntimeError, ValueError):
                    continue
        except (OSError, ValueError) as exc:
            return f"error: {exc}"
        found.sort(key=lambda x: -x[0])  # newest first, like ripgrep --sortr
        names = [n for _, n in found][offset : offset + limit]
        if not names:
            return f"(no files match {pattern!r})"
        return "\n".join(names)

    # --- content mode: regex inside files ---------------------------------
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"error: invalid regex: {exc}"

    def _iter_files():
        if base_files is not None:
            yield from base_files
            return
        for p in sorted(base.rglob(file_glob)):
            if p.is_file():
                yield p

    counts: dict[str, int] = {}
    files_seen: list[str] = []
    matches: list[str] = []
    skipped = 0
    truncated = False
    for p in _iter_files():
        try:
            if p.resolve() != root and root not in p.resolve().parents:
                continue
        except (OSError, RuntimeError):
            continue
        if has_binary_extension(str(p)):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = str(p.relative_to(root))
        file_hits = 0
        for lineno, line in enumerate(lines, 1):
            if not rx.search(line):
                continue
            file_hits += 1
            counts[rel] = counts.get(rel, 0) + 1
            if output_mode == "content":
                if skipped < offset:
                    skipped += 1
                    continue
                if len(matches) >= limit:
                    truncated = True
                    break
                if context > 0:
                    lo = max(0, lineno - 1 - context)
                    hi = min(len(lines), lineno + context)
                    block = "\n".join(f"{rel}:{j + 1}: {lines[j].rstrip()[:300]}" for j in range(lo, hi))
                    matches.append(block)
                else:
                    matches.append(f"{rel}:{lineno}: {line.rstrip()[:300]}")
        if file_hits and rel not in files_seen:
            files_seen.append(rel)
        if truncated:
            break

    if output_mode == "files_only":
        names = files_seen[offset : offset + limit]
        return "\n".join(names) if names else f"(no matches for {pattern!r})"
    if output_mode == "count":
        if not counts:
            return f"(no matches for {pattern!r})"
        rows = [f"{c:>6}  {name}" for name, c in sorted(counts.items(), key=lambda x: -x[1])]
        return "\n".join(rows[offset : offset + limit])
    if not matches:
        return f"(no matches for {pattern!r})"
    out = ("\n---\n" if context > 0 else "\n").join(matches)
    if truncated:
        out += f"\n… (more than {limit} matches; use offset/limit to page)"
    return out
