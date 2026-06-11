"""Binary-extension detection + in-process syntax linters.

Ported from the reference ``tools/binary_extensions.py`` and the in-process
linter functions in ``tools/file_operations.py``. The linters let
``write_file``/``patch`` surface only NEW syntax errors introduced by an edit
(pre-existing errors are filtered out), with zero subprocess overhead.
"""

from __future__ import annotations

BINARY_EXTENSIONS = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
    # Videos
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v", ".mpeg", ".mpg",
    # Audio
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".aiff", ".opus",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".z", ".tgz", ".iso",
    # Executables / binaries
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj", ".lib",
    ".app", ".msi", ".deb", ".rpm",
    # Office documents (pdf excluded — text-ish)
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Bytecode / VM artifacts
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear", ".node", ".wasm", ".rlib",
    # Databases
    ".sqlite", ".sqlite3", ".db", ".mdb", ".idx",
    # Design / 3D
    ".psd", ".ai", ".eps", ".sketch", ".fig", ".xd", ".blend", ".3ds", ".max",
    # Flash
    ".swf", ".fla",
    # Misc binary data
    ".lockb", ".dat", ".data",
})


def has_binary_extension(path: str) -> bool:
    """Return True if the path looks like a binary file (pure string check)."""
    dot = path.rfind(".")
    if dot == -1:
        return False
    return path[dot:].lower() in BINARY_EXTENSIONS


# --- in-process linters -----------------------------------------------------
# Each returns (ok, error_message). error == "__SKIP__" means no linter
# available (treat as no check).

def _lint_python(content: str) -> tuple[bool, str]:
    import ast
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        loc = f" (line {e.lineno}, column {e.offset})" if e.lineno else ""
        return False, f"{type(e).__name__}: {e.msg}{loc}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _lint_json(content: str) -> tuple[bool, str]:
    import json
    try:
        json.loads(content)
        return True, ""
    except json.JSONDecodeError as e:
        return False, f"JSONDecodeError: {e.msg} (line {e.lineno}, column {e.colno})"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _lint_yaml(content: str) -> tuple[bool, str]:
    try:
        import yaml
    except ImportError:
        return True, "__SKIP__"
    try:
        yaml.safe_load(content)
        return True, ""
    except yaml.YAMLError as e:
        return False, f"YAMLError: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _lint_toml(content: str) -> tuple[bool, str]:
    try:
        import tomllib as toml
    except ImportError:
        try:
            import tomli as toml  # type: ignore[no-redef]
        except ImportError:
            return True, "__SKIP__"
    try:
        toml.loads(content)
        return True, ""
    except Exception as e:  # noqa: BLE001 — TOMLDecodeError is a ValueError
        return False, f"{type(e).__name__}: {e}"


LINTERS_INPROC = {
    ".py": _lint_python,
    ".json": _lint_json,
    ".yaml": _lint_yaml,
    ".yml": _lint_yaml,
    ".toml": _lint_toml,
}


def lint_content(suffix: str, content: str) -> tuple[bool, str]:
    """Lint ``content`` for the given file ``suffix``.

    Returns (ok, message). ok is True when there's no linter for this type,
    the linter is unavailable, or the content is valid.
    """
    fn = LINTERS_INPROC.get(suffix.lower())
    if fn is None:
        return True, ""
    ok, msg = fn(content)
    if msg == "__SKIP__":
        return True, ""
    return ok, msg


def new_errors_only(suffix: str, old_content: str | None, new_content: str) -> str:
    """Return a lint error string only if the edit INTRODUCED a new error.

    If the file was already invalid before the edit, the error is pre-existing
    and not the agent's concern for this write — return empty.
    """
    ok_new, msg_new = lint_content(suffix, new_content)
    if ok_new:
        return ""
    if old_content is not None:
        ok_old, _ = lint_content(suffix, old_content)
        if not ok_old:
            return ""  # pre-existing error, not introduced by this edit
    return msg_new
