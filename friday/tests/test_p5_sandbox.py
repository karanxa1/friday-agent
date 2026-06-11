"""P5 verification: Docker sandbox (isolation + secret scrubbing)."""

from __future__ import annotations

import shutil

import pytest

from sandbox import docker_env

_HAVE_DOCKER = (shutil.which("docker") or shutil.which("podman")) is not None
pytestmark = pytest.mark.skipif(not _HAVE_DOCKER, reason="docker/podman not available")


def test_sandbox_status():
    assert "ready" in docker_env.sandbox_status()


def test_sandbox_python_runs():
    out = docker_env.sandbox_python("print(6*7)")
    assert "[exit 0]" in out and "42" in out


def test_sandbox_exec_runs_as_constrained_user():
    out = docker_env.sandbox_exec("echo hi")
    assert "[exit 0]" in out and "hi" in out


def test_sandbox_network_is_isolated():
    # --network none -> DNS resolution must fail inside the container.
    out = docker_env.sandbox_python(
        "import urllib.request; urllib.request.urlopen('http://example.com', timeout=5)"
    )
    assert "[exit 0]" not in out  # the script must have failed
    assert "name resolution" in out.lower() or "urlerror" in out.lower() or "failed" in out.lower()


def test_secret_env_is_scrubbed(monkeypatch):
    monkeypatch.setenv("MY_SECRET_TOKEN", "leak-me-please")
    out = docker_env.sandbox_python(
        "import os; print('FOUND' if 'MY_SECRET_TOKEN' in os.environ else 'CLEAN')"
    )
    assert "CLEAN" in out
