"""OSV malware screening for MCP extension packages (parity with the reference osv_check).

Before Friday registers an MCP server launched via ``npx``/``uvx``/``pipx``,
the package is checked against the free OSV.dev API for known-malicious
advisories (MAL-*). Fails open on network errors (availability over strictness)
but always audits the decision.
"""

from __future__ import annotations

import re

_ECOSYSTEM = {"npx": "npm", "uvx": "PyPI", "pipx": "PyPI"}
_PKG_RE = re.compile(r"^(@?[\w.-]+(?:/[\w.-]+)?)")


def package_from_command(command: str, args: list[str]) -> tuple[str, str] | None:
    """Extract (ecosystem, package) from an MCP launch command, if relevant."""
    eco = _ECOSYSTEM.get(command.rsplit("/", 1)[-1])
    if not eco:
        return None
    for a in args:
        if a.startswith("-"):  # skip flags like -y / --yes
            continue
        m = _PKG_RE.match(a)
        if m:
            # strip a pinned version suffix (pkg@1.2.3) but keep npm scopes
            pkg = m.group(1)
            return eco, pkg
    return None


def malware_advisories(command: str, args: list[str]) -> list[str]:
    """Return MAL-* advisory ids for the package, or [] (clean/not-checkable)."""
    import httpx

    from core import audit

    target = package_from_command(command, args)
    if target is None:
        return []
    eco, pkg = target
    try:
        resp = httpx.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": pkg, "ecosystem": eco}},
            timeout=8.0,
        )
        vulns = resp.json().get("vulns") or [] if resp.status_code == 200 else []
    except Exception:  # noqa: BLE001 — fail open, availability over strictness
        audit.log("security.osv_unreachable", package=pkg)
        return []
    bad = [v["id"] for v in vulns if str(v.get("id", "")).startswith("MAL-")]
    audit.log("security.osv_check", package=pkg, ecosystem=eco, malware=len(bad))
    return bad
