"""P7 verification: memory (frozen snapshot) + archive-only curator."""

from __future__ import annotations

import importlib
import tempfile
import time

import pytest


@pytest.fixture(autouse=True)
def temp_home(monkeypatch):
    d = tempfile.mkdtemp(prefix="friday-p7-")
    monkeypatch.setenv("FRIDAY_HOME", d)
    import core.config as cfg

    importlib.reload(cfg)
    import skills.usage as usage
    import memory.store as store
    import curator.curator as cur

    importlib.reload(usage)
    importlib.reload(store)
    importlib.reload(cur)
    yield d


def test_memory_add_and_limits():
    import memory.store as store

    assert "added" in store.memory_add("Friday prefers concise output.")
    assert "Friday prefers" in store.memory_show()
    # exceed limit
    big = "x" * 3000
    assert store.memory_add(big).startswith("error")


def test_memory_remove():
    import memory.store as store

    store.user_add("User name is Anuj.")
    assert "removed" in store.memory_remove("Anuj", kind="user")
    assert "Anuj" not in store.memory_show()


def test_frozen_snapshot_stable_across_edits():
    import memory.store as store

    store.memory_add("first entry")
    snap1 = store.load_snapshot()
    store.memory_add("second entry added after snapshot")
    snap2 = store.load_snapshot()
    # Snapshot is frozen on first load; later edits don't change it.
    assert snap1["memory"] == snap2["memory"]
    # but live show reflects the new entry
    assert "second entry" in store.memory_show()


def test_curator_only_archives_agent_created_stale():
    import skills.usage as usage
    import curator.curator as cur
    from core.config import settings

    # Create an agent skill dir + a user skill dir.
    (settings.skills_dir / "agent_skill").mkdir(parents=True)
    (settings.skills_dir / "agent_skill" / "SKILL.md").write_text("---\nname: a\ndescription: d\n---\n")
    (settings.skills_dir / "user_skill").mkdir(parents=True)
    (settings.skills_dir / "user_skill" / "SKILL.md").write_text("---\nname: u\ndescription: d\n---\n")
    usage.mark_created("agent_skill", by="agent")
    usage.mark_created("user_skill", by="user")

    # Make the agent skill very old.
    old = time.time() - (200 * 86400)
    data = usage.all_entries()
    data["agent_skill"]["last_activity_at"] = old
    data["user_skill"]["last_activity_at"] = old
    usage._save(data)

    result = cur.apply_automatic_transitions()
    assert "agent_skill" in result["archived"]
    assert "user_skill" not in result["archived"]  # user skills are off-limits
    # archived dir contains it
    assert (settings.archive_dir / "agent_skill").is_dir()


def test_curator_seeds_then_runs():
    import curator.curator as cur

    first = cur.run()
    assert first["ran"] is False and first["reason"] == "seeded_first_run"
    forced = cur.run(force=True)
    assert forced["ran"] is True
