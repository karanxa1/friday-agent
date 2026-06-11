"""Skill manager + two-tier read tools (inspired by Friday' skill_manager_tool / skills_tool).

Skills are procedural memory: a directory ``<skills_dir>/<name>/SKILL.md`` with
YAML frontmatter (``name`` + ``description`` required) plus optional support
dirs (references/templates/scripts/assets).

Write side  : ``skill_create`` / ``skill_edit`` / ``skill_patch`` / ``skill_delete``
Read side   : ``skill_list`` (tier-1 metadata) / ``skill_view`` (full content)

Agent-origin creates are marked via the provenance ContextVar so the curator
can manage them.
"""

from __future__ import annotations

import re
from pathlib import Path

from core import audit
from core.config import settings
from core.registry import tool
from skills import usage
from skills.provenance import is_background_review

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MAX_CONTENT = 100_000


def _validate_name(name: str) -> str | None:
    if not name or not _NAME_RE.match(name):
        return f"invalid skill name {name!r}: must match {_NAME_RE.pattern}"
    return None


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Very small YAML-frontmatter parser (name/description only)."""
    out: dict[str, str] = {}
    if not text.startswith("---"):
        return out
    end = text.find("\n---", 3)
    if end == -1:
        return out
    block = text[3:end].strip()
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _validate_frontmatter(text: str) -> str | None:
    fm = _parse_frontmatter(text)
    if "name" not in fm or "description" not in fm:
        return "SKILL.md must start with YAML frontmatter containing 'name' and 'description'"
    return None


def _skill_dir(name: str) -> Path:
    return settings.skills_dir / name


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _fuzzy_replace(haystack: str, old: str, new: str) -> tuple[str, bool]:
    """Exact match first; then whitespace-tolerant match (Friday-style patch)."""
    if old in haystack:
        return haystack.replace(old, new, 1), True
    # Whitespace-normalized fallback.
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    target = norm(old)
    lines = haystack.splitlines(keepends=True)
    for window in range(len(lines), 0, -1):
        for i in range(len(lines) - window + 1):
            chunk = "".join(lines[i : i + window])
            if norm(chunk) == target:
                return haystack[: sum(len(x) for x in lines[:i])] + new + haystack[
                    sum(len(x) for x in lines[: i + window]) :
                ], True
    return haystack, False


# --- write tools ------------------------------------------------------------


@tool("skills", description="Create a new skill (procedural memory) with SKILL.md content.")
def skill_create(name: str, content: str) -> str:
    """Create a skill directory with a SKILL.md.

    Args:
        name: lowercase skill id (a-z, 0-9, . _ -).
        content: full SKILL.md text, must start with YAML frontmatter
                 containing 'name' and 'description'.
    """
    err = _validate_name(name) or _validate_frontmatter(content)
    if err:
        return f"error: {err}"
    if len(content) > _MAX_CONTENT:
        return f"error: content exceeds {_MAX_CONTENT} chars"
    from core.threat_patterns import scan_or_error

    if threat := scan_or_error(content, f"skill {name!r}"):
        return threat
    skill_md = _skill_dir(name) / "SKILL.md"
    if skill_md.exists():
        return f"error: skill {name!r} already exists (use skill_edit/skill_patch)"
    _atomic_write(skill_md, content)
    by = "agent" if is_background_review() else "user"
    usage.mark_created(name, by=by)
    audit.log("skill.create", name=name, created_by=by, bytes=len(content))
    return f"created skill {name!r} (created_by={by})"


@tool("skills", description="Replace a skill's SKILL.md content entirely.")
def skill_edit(name: str, content: str) -> str:
    """Overwrite an existing skill's SKILL.md.

    Args:
        name: skill id.
        content: new full SKILL.md text (frontmatter required).
    """
    err = _validate_name(name) or _validate_frontmatter(content)
    if err:
        return f"error: {err}"
    from core.threat_patterns import scan_or_error

    if threat := scan_or_error(content, f"skill {name!r}"):
        return threat
    skill_md = _skill_dir(name) / "SKILL.md"
    if not skill_md.exists():
        return f"error: skill {name!r} not found"
    _atomic_write(skill_md, content)
    usage.bump(name, "patch_count")
    audit.log("skill.edit", name=name, bytes=len(content))
    return f"edited skill {name!r}"


@tool("skills", description="Patch a skill's SKILL.md via find-and-replace (whitespace tolerant).")
def skill_patch(name: str, old: str, new: str) -> str:
    """Apply a targeted find/replace to a skill's SKILL.md.

    Args:
        name: skill id.
        old: text to find (exact or whitespace-normalized).
        new: replacement text.
    """
    if _validate_name(name):
        return f"error: {_validate_name(name)}"
    skill_md = _skill_dir(name) / "SKILL.md"
    if not skill_md.exists():
        return f"error: skill {name!r} not found"
    text = skill_md.read_text(encoding="utf-8")
    patched, ok = _fuzzy_replace(text, old, new)
    if not ok:
        return f"error: could not locate the 'old' text in {name!r}"
    if err := _validate_frontmatter(patched):
        return f"error: patch would break frontmatter: {err}"
    _atomic_write(skill_md, patched)
    usage.bump(name, "patch_count")
    audit.log("skill.patch", name=name)
    return f"patched skill {name!r}"


@tool("skills", description="Delete a skill (refused if pinned).")
def skill_delete(name: str) -> str:
    """Delete a skill directory. Pinned skills are refused.

    Args:
        name: skill id.
    """
    import shutil

    if _validate_name(name):
        return f"error: {_validate_name(name)}"
    info = usage.get(name)
    if info and info.get("pinned"):
        return f"error: skill {name!r} is pinned; unpin before delete"
    d = _skill_dir(name)
    if not d.exists():
        return f"error: skill {name!r} not found"
    shutil.rmtree(d)
    usage.forget(name)
    audit.log("skill.delete", name=name)
    return f"deleted skill {name!r}"


# --- read tools -------------------------------------------------------------


def seed_builtin_skills() -> int:
    """Copy the bundled starter skills into the skills dir if absent.

    Idempotent — only seeds a skill whose directory does not already exist, so
    user edits and the curator are never overwritten.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parent / "builtin"
    if not src.is_dir():
        return 0
    dest_base = settings.skills_dir
    dest_base.mkdir(parents=True, exist_ok=True)
    seeded = 0
    for child in sorted(src.iterdir()):
        md = child / "SKILL.md"
        if not md.is_file() or (dest_base / child.name).exists():
            continue
        try:
            (dest_base / child.name).mkdir(parents=True, exist_ok=True)
            (dest_base / child.name / "SKILL.md").write_text(
                md.read_text(encoding="utf-8"), encoding="utf-8"
            )
            seeded += 1
        except OSError:
            pass
    return seeded


def _iter_skills():
    base = settings.skills_dir
    if not base.exists():
        return
    for child in sorted(base.iterdir()):
        if child.name.startswith("."):
            continue
        md = child / "SKILL.md"
        if md.is_file():
            yield child.name, md


@tool("skills", description="List available skills with name + description (metadata only).")
def skill_list() -> str:
    """List all skills (tier-1: name + one-line description)."""
    rows = []
    for name, md in _iter_skills():
        fm = _parse_frontmatter(md.read_text(encoding="utf-8")[:4000])
        rows.append(f"- {name}: {fm.get('description', '(no description)')}")
    if not rows:
        return "(no skills yet)"
    return "\n".join(rows)


@tool("skills", description="View a skill's full SKILL.md content by name.")
def skill_view(name: str) -> str:
    """Return a skill's full SKILL.md text (tier-2).

    Args:
        name: skill id.
    """
    if _validate_name(name):
        return f"error: {_validate_name(name)}"
    md = _skill_dir(name) / "SKILL.md"
    if not md.is_file():
        return f"error: skill {name!r} not found"
    usage.bump(name, "view_count")
    return md.read_text(encoding="utf-8")
