"""P23: background autonomous tasks (Manus-style)."""

from __future__ import annotations

import importlib
import json

import pytest


async def _fake_stream(*args, **kwargs):
    yield 'data: {"type": "start", "agent": "root"}\n\n'
    yield 'data: {"type": "tool_call", "name": "run_python", "id": "1", "agent": "root"}\n\n'
    yield 'data: {"type": "tool_result", "name": "run_python", "ok": true, "id": "1"}\n\n'
    yield 'data: {"type": "token", "text": "Hello "}\n\n'
    yield 'data: {"type": "token", "text": "world"}\n\n'
    yield 'data: {"type": "done", "tool_calls": 1}\n\n'


@pytest.fixture
def tasks_mod(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    from core import tasks as t

    importlib.reload(t)  # fresh in-memory store, tmp-home persistence
    import control_plane.streaming as streaming

    monkeypatch.setattr(streaming, "stream_agent", _fake_stream)
    return t


def test_submit_runs_and_records_output_and_events(tasks_mod):
    # No running loop in a sync test -> submit() runs the task to completion.
    s = tasks_mod.submit("build me a thing")
    tid = s["id"]
    t = tasks_mod.get_task(tid)
    assert t["status"] == "done"
    assert t["output"] == "Hello world"
    assert any(e["type"] == "tool_call" and e["name"] == "run_python" for e in t["events"])


def test_list_and_summary(tasks_mod):
    s = tasks_mod.submit("goal one")
    listed = tasks_mod.list_tasks()
    assert listed[0]["id"] == s["id"]
    assert listed[0]["tool_calls"] >= 1
    assert "output" not in listed[0]  # summaries are compact


def test_empty_goal_rejected(tasks_mod):
    with pytest.raises(ValueError):
        tasks_mod.submit("   ")


def test_running_task_marked_interrupted_on_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_HOME", str(tmp_path))
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks.json").write_text(
        json.dumps({"abc": {"id": "abc", "goal": "g", "status": "running",
                            "created": "2026-01-01T00:00:00+00:00", "events": []}}),
        encoding="utf-8",
    )
    from core import tasks as t

    importlib.reload(t)
    assert t.get_task("abc")["status"] == "interrupted"
