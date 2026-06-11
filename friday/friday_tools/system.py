"""System toolset: run shell commands, find files, and search content.

This is the "everything" capability — it lets Friday execute arbitrary shell
commands and search the filesystem, complementing the sandboxed ``files``
toolset (read/write/edit) and the approval-gated ``self_dev`` toolset.

All operations are confined to ``settings.file_root`` (the same root the
``files`` toolset uses). By default that is the agent's workspace
(``~/.friday/workspace``); operators can widen it to the project tree or home
via ``FRIDAY_FILE_ROOT`` (see core/config.py). The cwd guard resolves with
symlinks followed so a command cannot be launched from outside the root.

Commands run with a wall-clock timeout and a captured-output cap so a runaway
process cannot hang the agent or flood the model context. Every command is
audit-logged (the command string is truncated; treat external content as
untrusted).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool

_MAX_OUTPUT = 30_000
_DEFAULT_TIMEOUT = 120
_MAX_TIMEOUT = 600
_MAX_MATCHES = 200


def _root() -> Path:
    root = settings.file_root
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_dir(rel: str) -> Path | None:
    """Resolve a directory ``rel`` inside the file root; None if it escapes."""
    if os.path.isabs(rel):
        return None
    root = _root()
    candidate = root / rel
    try:
        target = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    if target != root and root not in target.parents:
        return None
    return target


def _clip(text: str) -> str:
    if len(text) > _MAX_OUTPUT:
        return text[:_MAX_OUTPUT] + f"\n… (truncated, {len(text)} chars total)"
    return text


@tool(
    "system",
    description="Run a shell command inside the agent's file root and return its output.",
)
def run_command(command: str, cwd: str = ".", timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Execute a shell command and return combined stdout/stderr.

    The command runs with the working directory confined to the agent's file
    root. It is killed if it exceeds ``timeout`` seconds, and its output is
    capped to keep the model context manageable.

    Args:
        command: the shell command line to execute.
        cwd: working directory relative to the file root (default: root).
        timeout: wall-clock timeout in seconds (capped at 600).
    """
    if not command.strip():
        return "error: empty command"
    work = _safe_dir(cwd)
    if work is None:
        return f"error: cwd {cwd!r} escapes the file root"
    if not work.is_dir():
        return f"error: cwd {cwd!r} is not a directory"
    timeout = max(1, min(int(timeout or _DEFAULT_TIMEOUT), _MAX_TIMEOUT))
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        audit.log("system.run.timeout", command=command[:200], timeout=timeout)
        return f"error: command timed out after {timeout}s"
    except OSError as exc:
        return f"error: {exc}"
    audit.log("system.run", command=command[:200], code=proc.returncode)
    out = (proc.stdout or "") + (proc.stderr or "")
    header = f"exit code: {proc.returncode}\n"
    body = out.strip() or "(no output)"
    return header + _clip(body)


@tool("system", description="Find files matching a glob pattern under the file root.")
def glob_files(pattern: str, path: str = ".") -> str:
    """List files matching a glob ``pattern`` (e.g. '**/*.py').

    Args:
        pattern: a glob pattern, relative to ``path`` (supports ** recursion).
        path: directory to search from, relative to the file root.
    """
    base = _safe_dir(path)
    if base is None:
        return f"error: path {path!r} escapes the file root"
    if not base.is_dir():
        return f"error: {path!r} is not a directory"
    root = _root()
    matches: list[str] = []
    try:
        for p in base.glob(pattern):
            try:
                resolved = p.resolve()
                if resolved != root and root not in resolved.parents:
                    continue  # symlink escape
                matches.append(str(p.relative_to(root)))
            except (OSError, RuntimeError, ValueError):
                continue
            if len(matches) >= _MAX_MATCHES:
                break
    except (OSError, ValueError) as exc:
        return f"error: {exc}"
    if not matches:
        return f"(no files match {pattern!r})"
    matches.sort()
    suffix = f"\n… ({_MAX_MATCHES}+ matches, truncated)" if len(matches) >= _MAX_MATCHES else ""
    return "\n".join(matches) + suffix


@tool("system", description="Search file contents for a regex under the file root.")
def grep_files(pattern: str, path: str = ".", include: str = "*") -> str:
    """Search files for lines matching a regular expression.

    Args:
        pattern: a Python regular expression to search for.
        path: directory to search from, relative to the file root.
        include: glob filter on file names (default: all files).
    """
    base = _safe_dir(path)
    if base is None:
        return f"error: path {path!r} escapes the file root"
    if not base.is_dir():
        return f"error: {path!r} is not a directory"
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"error: invalid regex: {exc}"
    root = _root()
    hits: list[str] = []
    for p in sorted(base.rglob(include)):
        if not p.is_file():
            continue
        try:
            resolved = p.resolve()
            if resolved != root and root not in resolved.parents:
                continue  # symlink escape
        except (OSError, RuntimeError):
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if rx.search(line):
                        rel = p.relative_to(root)
                        hits.append(f"{rel}:{lineno}: {line.rstrip()[:300]}")
                        if len(hits) >= _MAX_MATCHES:
                            break
        except OSError:
            continue
        if len(hits) >= _MAX_MATCHES:
            break
    if not hits:
        return f"(no matches for {pattern!r})"
    suffix = f"\n… ({_MAX_MATCHES}+ matches, truncated)" if len(hits) >= _MAX_MATCHES else ""
    return _clip("\n".join(hits)) + suffix
