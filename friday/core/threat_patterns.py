"""Injection threat scanning (parity with the reference tools/threat_patterns.py).

Lightweight regex screening for prompt-injection / exfiltration payloads in
untrusted text before it reaches the model: skill bodies, memory entries, and
scheduled-job prompts. This is a tripwire, not a guarantee — findings are
surfaced and audited so a human can review.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_override",
        re.compile(
            r"(?i)\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)"
        ),
    ),
    (
        "role_hijack",
        re.compile(r"(?i)\byou\s+are\s+(now|no\s+longer)\b.{0,40}\b(assistant|agent|ai|model)\b"),
    ),
    (
        "system_prompt_probe",
        re.compile(r"(?i)\b(reveal|print|show|repeat|output)\b.{0,30}\b(system\s+prompt|instructions)\b"),
    ),
    (
        "secret_exfiltration",
        re.compile(r"(?i)\b(send|post|upload|exfiltrate|forward)\b.{0,40}\b(api[_\s-]?key|credential|secret|token|password)s?\b"),
    ),
    (
        "gate_bypass",
        re.compile(r"(?i)\b(bypass|skip|disable|circumvent)\b.{0,30}\b(approval|gate|safety|guard|sandbox)\b"),
    ),
    (
        "hidden_directive",
        re.compile(r"(?i)<\s*(system|admin|important)\s*>|\[\s*system\s+override\s*\]"),
    ),
]


def scan_text(text: str) -> list[str]:
    """Return the names of threat patterns found in ``text`` (empty = clean)."""
    if not text:
        return []
    return [name for name, pat in _PATTERNS if pat.search(text)]


def scan_or_error(text: str, source: str) -> str | None:
    """Audit + describe findings, or None if the text is clean."""
    findings = scan_text(text)
    if not findings:
        return None
    from core import audit

    audit.log("security.injection_flagged", source=source, patterns=",".join(findings))
    return (
        f"error: {source} flagged by injection screening ({', '.join(findings)}). "
        f"Rephrase the content or have the user review it."
    )
