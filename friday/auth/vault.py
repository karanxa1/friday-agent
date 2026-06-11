"""Encrypted credential vault + auth-request flow (inspired by the reference credential tools).

Secrets the agent needs (API keys, tokens) are stored encrypted at rest under
``~/.friday/vault.enc`` using Fernet (AES-128-CBC + HMAC). The encryption key
lives in ``~/.friday/vault.key`` (chmod 600) -- created on first use.

The agent never sees raw secret values: it references them by *name*. A pending
"credential request" is surfaced to the UI so a human supplies the value out of
band; ``set_credential`` stores it; tools read it via ``get_credential`` only
when actually calling an external service.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet

from core import audit
from core.config import settings

_LOCK = threading.RLock()


def _key_path() -> Path:
    settings.ensure_home()
    return settings.home / "vault.key"


def _vault_path() -> Path:
    settings.ensure_home()
    return settings.home / "vault.enc"


def _fernet() -> Fernet:
    kp = _key_path()
    if not kp.is_file():
        key = Fernet.generate_key()
        # Create with 0600 atomically so the key is never briefly world-readable.
        # NOTE: the key sits beside vault.enc, so this protects against casual
        # inspection, not an attacker who can read ~/.friday. Use a KMS/keyring
        # for real at-rest protection.
        try:
            fd = os.open(kp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, key)
            finally:
                os.close(fd)
        except FileExistsError:
            pass  # created concurrently; fall through to read
    return Fernet(kp.read_bytes())


def _load() -> dict[str, str]:
    p = _vault_path()
    if not p.is_file():
        return {}
    try:
        raw = _fernet().decrypt(p.read_bytes())
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - corrupt/unreadable vault -> empty
        return {}


def _save(data: dict[str, str]) -> None:
    token = _fernet().encrypt(json.dumps(data).encode("utf-8"))
    p = _vault_path()
    tmp = p.with_suffix(".enc.tmp")
    tmp.write_bytes(token)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(p)


def set_credential(name: str, value: str) -> None:
    """Store/overwrite a secret by name (encrypted)."""
    with _LOCK:
        data = _load()
        data[name] = value
        _save(data)
    audit.log("vault.set", name=name)  # value never logged


def get_credential(name: str) -> str | None:
    """Retrieve a secret value by name (for use at the call site only)."""
    with _LOCK:
        return _load().get(name)


def has_credential(name: str) -> bool:
    with _LOCK:
        return name in _load()


def list_credentials() -> list[str]:
    """Return the *names* of stored credentials (never values)."""
    with _LOCK:
        return sorted(_load().keys())


def delete_credential(name: str) -> bool:
    with _LOCK:
        data = _load()
        if name in data:
            del data[name]
            _save(data)
            audit.log("vault.delete", name=name)
            return True
    return False
