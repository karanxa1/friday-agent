"""Self-development toolset: the agent edits its own codebase, safely.

Inspired by Friday' file tools + write_approval gate, adapted so Friday
can modify itself:

* ``read_self``       -- read a project file
* ``write_self``      -- stage a full-file write (approval-gated), git-backed
* ``edit_self``       -- stage a find/replace edit (approval-gated)
* ``validate_self``   -- syntax-check (py_compile) + optional ruff
* ``git_snapshot``    -- commit current state
* ``git_revert``      -- revert to a prior commit (approval-gated)
* ``reload_module``   -- hot-reload an edited module (importlib.reload)
* ``apply_pending``   -- apply an approved write/edit, snapshot, and reload

All writes are scoped to the project root; nothing outside it can be touched.
Every applied change is a git commit, so any edit is revertable.
"""

from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

from core import audit
from core.registry import tool
from control_plane import approvals


def _root() -> Path:
    """Project root the agent may edit. Override with FRIDAY_SELFDEV_ROOT (tests)."""
    override = os.environ.get("FRIDAY_SELFDEV_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parent.parent


def _git_root() -> Path:
    """Directory to run git in. Override with FRIDAY_SELFDEV_GIT_ROOT (tests)."""
    override = os.environ.get("FRIDAY_SELFDEV_GIT_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return _root().parent  # repo root is hack-agent/


def _safe_path(rel: str) -> Path | None:
    """Resolve ``rel`` under the project root; reject traversal/escape."""
    root = _root()
    p = (root / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(_git_root()),
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


@tool("self_dev", description="Read a project file by path relative to the project root.")
def read_self(path: str) -> str:
    """Read a file inside the Friday project.

    Args:
        path: path relative to the project root (e.g. 'core/model.py').
    """
    p = _safe_path(path)
    if p is None:
        return f"error: path {path!r} escapes the project root"
    if not p.is_file():
        return f"error: file {path!r} not found"
    return p.read_text(encoding="utf-8")


@tool("self_dev", description="Stage a full-file write to a project file (requires approval).")
def write_self(path: str, content: str) -> str:
    """Stage a self-modification (full file write). Returns an approval id.

    Args:
        path: project-relative path to write.
        content: the new full file content.
    """
    p = _safe_path(path)
    if p is None:
        return f"error: path {path!r} escapes the project root"
    entry = approvals.submit(
        "self_edit",
        summary=f"write {path} ({len(content)} bytes)",
        payload={"op": "write", "path": path, "content": content},
    )
    return f"staged self-edit {entry['id']} (status={entry['status']}). Use apply_pending to apply once approved."


@tool("self_dev", description="Stage a find/replace edit to a project file (requires approval).")
def edit_self(path: str, old: str, new: str) -> str:
    """Stage a self-modification (find/replace). Returns an approval id.

    Args:
        path: project-relative path.
        old: exact text to find.
        new: replacement text.
    """
    p = _safe_path(path)
    if p is None:
        return f"error: path {path!r} escapes the project root"
    if not p.is_file():
        return f"error: file {path!r} not found"
    text = p.read_text(encoding="utf-8")
    if old not in text:
        return f"error: 'old' text not found in {path!r}"
    entry = approvals.submit(
        "self_edit",
        summary=f"edit {path} (replace {len(old)}->{len(new)} chars)",
        payload={"op": "edit", "path": path, "old": old, "new": new},
    )
    return f"staged self-edit {entry['id']} (status={entry['status']}). Use apply_pending to apply once approved."


@tool("self_dev", description="Validate a Python project file (py_compile + ruff if available).")
def validate_self(path: str) -> str:
    """Syntax-check a Python file and lint it if ruff is installed.

    Args:
        path: project-relative .py path.
    """
    p = _safe_path(path)
    if p is None or not p.is_file():
        return f"error: file {path!r} not found"
    import py_compile

    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as exc:
        return f"SYNTAX ERROR: {exc}"
    # Optional ruff.
    proc = subprocess.run(["ruff", "check", str(p)], capture_output=True, text=True, cwd=str(_root()))
    if proc.returncode == 0:
        return "ok: syntax valid; ruff clean"
    return f"syntax valid; ruff findings:\n{(proc.stdout + proc.stderr).strip()[:2000]}"


@tool("self_dev", description="Commit the current project state to git with a message.")
def git_snapshot(message: str) -> str:
    """Create a git commit of the current state.

    Args:
        message: commit message.
    """
    _git("add", "-A")
    code, out = _git("commit", "-m", f"[self-dev] {message}")
    audit.log("self_dev.snapshot", message=message, code=code)
    return out or ("committed" if code == 0 else "nothing to commit")


@tool("self_dev", description="Revert the repo to a prior commit ref (requires approval).")
def git_revert(ref: str) -> str:
    """Stage a git revert to a prior commit (approval-gated).

    Args:
        ref: a commit hash or ref to reset to.
    """
    entry = approvals.submit("self_revert", summary=f"git reset --hard {ref}", payload={"ref": ref})
    return f"staged revert {entry['id']} (status={entry['status']}). Approve, then apply_pending."


@tool("self_dev", description="Hot-reload a project module by dotted path after an edit.")
def reload_module(dotted_path: str) -> str:
    """Re-import an edited module so changes take effect without restart.

    Args:
        dotted_path: e.g. 'core.builtin_tools'.
    """
    try:
        mod = importlib.import_module(dotted_path)
        importlib.reload(mod)
        audit.log("self_dev.reload", module=dotted_path)
        return f"reloaded {dotted_path}"
    except Exception as exc:  # noqa: BLE001
        return f"error reloading {dotted_path}: {type(exc).__name__}: {exc}"


@tool("self_dev", description="Apply an approved self-edit/revert: write file, validate, commit, reload.")
def apply_pending(action_id: str) -> str:
    """Apply a previously-approved self-modification.

    Args:
        action_id: the approval id returned by write_self/edit_self/git_revert.
    """
    if not approvals.is_approved(action_id):
        return f"error: action {action_id!r} is not approved (status pending/rejected)"
    entry = approvals.get(action_id)
    if entry is None:
        return f"error: action {action_id!r} not found"
    payload = entry["payload"]

    if entry["type"] == "self_revert":
        code, out = _git("reset", "--hard", payload["ref"])
        approvals.mark_applied(action_id)
        return f"revert applied: {out}" if code == 0 else f"revert failed: {out}"

    # self_edit (write or edit)
    path = payload["path"]
    p = _safe_path(path)
    if p is None:
        return f"error: path {path!r} escapes root"
    if payload["op"] == "write":
        new_content = payload["content"]
    else:  # edit
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        if payload["old"] not in text:
            return f"error: 'old' text no longer present in {path!r}"
        new_content = text.replace(payload["old"], payload["new"], 1)

    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    tmp.replace(p)

    # Validate if Python.
    if p.suffix == ".py":
        result = validate_self(path)
        if result.startswith("SYNTAX ERROR"):
            return f"applied write but {result}; fix before relying on it"

    git_snapshot(f"apply {action_id}: {entry['summary']}")
    approvals.mark_applied(action_id)
    audit.log("self_dev.applied", id=action_id, path=path)
    return f"applied {action_id} to {path}; committed. Reload the module if needed."
