"""Docker sandbox: Friday's isolated "computer" for arbitrary code execution.

Inspired by the reference tools/environments/docker.py + code_execution_tool secret
scrubbing. Runs commands/code in a hardened, resource-limited container:

  --network none (default)  --cap-drop ALL  --security-opt no-new-privileges
  --pids-limit 256  --memory/--cpus caps  read-only-ish workspace bind mount

The container is the security boundary; the agent never executes on the host.
Secrets are scrubbed from the child env (the reference _SECRET_SUBSTRINGS pattern).

Tools:
  ``sandbox_exec(command)``  -- run a shell command in the container
  ``sandbox_python(code)``   -- run a Python snippet in the container
  ``sandbox_status()``       -- report docker availability + image

If Docker is unavailable the tools return a clear error rather than falling
back to host execution (no silent unsafe path).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from core import audit
from core.registry import tool

_IMAGE = "python:3.13-slim"
_SECRET_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "DSN", "WEBHOOK", "AUTH", "CREDENTIAL")

_BASE_SECURITY_ARGS = [
    "--network", "none",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--user", "65534:65534",  # nobody:nogroup — never run as root in-container
    "--pids-limit", "256",
    "--memory", "512m",
    "--cpus", "1",
    "--read-only",
    "--tmpfs", "/tmp:rw,nosuid,size=64m",
]


def _docker() -> str | None:
    return shutil.which("docker") or shutil.which("podman")


def _scrubbed_env() -> dict[str, str]:
    """Minimal env with no secret-bearing variables (reference pattern)."""
    import os

    safe = {}
    for k, v in os.environ.items():
        if any(s in k.upper() for s in _SECRET_SUBSTRINGS):
            continue
        if k in ("PATH", "HOME", "LANG", "LC_ALL", "TERM"):
            safe[k] = v
    safe.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    safe.setdefault("HOME", "/tmp")
    return safe


def _run_in_container(argv: list[str], *, mount: Path | None = None, timeout: int = 120) -> tuple[int, str]:
    docker = _docker()
    if not docker:
        return 1, "error: docker/podman not available on this host"

    cmd = [docker, "run", "--rm", *_BASE_SECURITY_ARGS]
    # Pass scrubbed env explicitly.
    for k, v in _scrubbed_env().items():
        cmd += ["--env", f"{k}={v}"]
    if mount is not None:
        cmd += ["--volume", f"{mount}:/work:ro", "--workdir", "/work"]
    cmd += [_IMAGE, *argv]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"error: command timed out after {timeout}s"
    except OSError as exc:
        return 1, f"error launching container: {exc}"
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode, out[:50_000]


@tool("sandbox", description="Run a shell command inside a hardened Docker container (no network).")
def sandbox_exec(command: str, timeout: int = 120) -> str:
    """Execute a shell command in an isolated container.

    Args:
        command: the shell command to run.
        timeout: max seconds (default 120).
    """
    code, out = _run_in_container(["sh", "-c", command], timeout=timeout)
    audit.log("sandbox.exec", command=command[:200], code=code)
    return f"[exit {code}]\n{out}"


@tool("sandbox", description="Run a Python snippet inside a hardened Docker container (no network).")
def sandbox_python(code: str, timeout: int = 120) -> str:
    """Execute Python code in an isolated container.

    Args:
        code: Python source to run.
        timeout: max seconds (default 120).
    """
    # Write code to a temp dir mounted read-only at /work.
    tmp = Path(tempfile.mkdtemp(prefix="friday-sandbox-"))
    (tmp / "snippet.py").write_text(code, encoding="utf-8")
    try:
        rc, out = _run_in_container(["python", "/work/snippet.py"], mount=tmp, timeout=timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    audit.log("sandbox.python", code_len=len(code), code=rc)
    return f"[exit {rc}]\n{out}"


@tool("sandbox", description="Report Docker sandbox availability and image.")
def sandbox_status() -> str:
    """Check whether the Docker sandbox is usable."""
    docker = _docker()
    if not docker:
        return "sandbox unavailable: docker/podman not found"
    return f"sandbox ready: {docker} (image {_IMAGE})"
