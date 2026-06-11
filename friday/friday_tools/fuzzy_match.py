"""Fuzzy find-and-replace (ported from the reference ``tools/fuzzy_match.py``).

A multi-strategy matching chain that robustly locates ``old_string`` inside a
file even when whitespace, indentation, escape sequences, or unicode
punctuation differ slightly from what the model emitted. The strategies are
tried in order from strictest (exact) to loosest (line-similarity), so a
confident exact match always wins.

Public API:
    fuzzy_find_and_replace(content, old_string, new_string, replace_all)
        -> (new_content, match_count, strategy_name, error_message)
    find_closest_lines(old_string, content) -> str   # "did you mean?" hint
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# Unicode punctuation that models frequently substitute for ASCII. Normalizing
# these lets a paste-with-smart-quotes still match the ASCII source.
_UNICODE_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "--", "\u2026": "...", "\u00a0": " ",
}


def _unicode_normalize(text: str) -> str:
    for src, dst in _UNICODE_MAP.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFC", text)


def _calc_positions(content_lines: list[str], start_line: int, end_line: int, content_length: int) -> tuple[int, int]:
    start_pos = sum(len(line) + 1 for line in content_lines[:start_line])
    end_pos = sum(len(line) + 1 for line in content_lines[:end_line]) - 1
    return start_pos, min(content_length, end_pos)


def _find_normalized_matches(
    content: str,
    content_lines: list[str],
    content_normalized_lines: list[str],
    pattern_normalized: str,
) -> list[tuple[int, int]]:
    pattern_norm_lines = pattern_normalized.split("\n")
    n = len(pattern_norm_lines)
    out: list[tuple[int, int]] = []
    for i in range(len(content_normalized_lines) - n + 1):
        block = "\n".join(content_normalized_lines[i : i + n])
        if block == pattern_normalized:
            out.append(_calc_positions(content_lines, i, i + n, len(content)))
    return out


# --- strategies -------------------------------------------------------------

def _strategy_exact(content: str, pattern: str) -> list[tuple[int, int]]:
    matches, start = [], 0
    while True:
        pos = content.find(pattern, start)
        if pos == -1:
            break
        matches.append((pos, pos + len(pattern)))
        start = pos + 1
    return matches


def _strategy_line_trimmed(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_normalized = "\n".join(line.strip() for line in pattern.split("\n"))
    content_lines = content.split("\n")
    return _find_normalized_matches(
        content, content_lines, [line.strip() for line in content_lines], pattern_normalized
    )


def _strategy_whitespace_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    norm = lambda s: re.sub(r"[ \t]+", " ", s)
    pattern_normalized = norm(pattern)
    content_normalized = norm(content)
    norm_matches = _strategy_exact(content_normalized, pattern_normalized)
    if not norm_matches:
        return []
    return _map_normalized_positions(content, content_normalized, norm_matches)


def _strategy_indentation_flexible(content: str, pattern: str) -> list[tuple[int, int]]:
    content_lines = content.split("\n")
    pattern_normalized = "\n".join(line.lstrip() for line in pattern.split("\n"))
    return _find_normalized_matches(
        content, content_lines, [line.lstrip() for line in content_lines], pattern_normalized
    )


def _strategy_escape_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    unescaped = pattern.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")
    if unescaped == pattern:
        return []
    return _strategy_exact(content, unescaped)


def _strategy_trimmed_boundary(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_lines = pattern.split("\n")
    if not pattern_lines:
        return []
    pattern_lines[0] = pattern_lines[0].strip()
    if len(pattern_lines) > 1:
        pattern_lines[-1] = pattern_lines[-1].strip()
    modified = "\n".join(pattern_lines)
    content_lines = content.split("\n")
    n = len(pattern_lines)
    out: list[tuple[int, int]] = []
    for i in range(len(content_lines) - n + 1):
        block = content_lines[i : i + n].copy()
        block[0] = block[0].strip()
        if len(block) > 1:
            block[-1] = block[-1].strip()
        if "\n".join(block) == modified:
            out.append(_calc_positions(content_lines, i, i + n, len(content)))
    return out


def _strategy_unicode_normalized(content: str, pattern: str) -> list[tuple[int, int]]:
    norm_content = _unicode_normalize(content)
    norm_pattern = _unicode_normalize(pattern)
    if norm_content == content and norm_pattern == pattern:
        return []
    matches = _strategy_exact(norm_content, norm_pattern)
    if not matches:
        # fall back to line-trimmed on the normalized text
        matches = _strategy_line_trimmed(norm_content, norm_pattern)
    if not matches:
        return []
    return _map_normalized_positions(content, norm_content, matches)


def _strategy_block_anchor(content: str, pattern: str) -> list[tuple[int, int]]:
    norm_pattern = _unicode_normalize(pattern)
    norm_content = _unicode_normalize(content)
    pattern_lines = norm_pattern.split("\n")
    if len(pattern_lines) < 2:
        return []
    first_line, last_line = pattern_lines[0].strip(), pattern_lines[-1].strip()
    norm_content_lines = norm_content.split("\n")
    orig_content_lines = content.split("\n")
    n = len(pattern_lines)
    potential = [
        i
        for i in range(len(norm_content_lines) - n + 1)
        if norm_content_lines[i].strip() == first_line and norm_content_lines[i + n - 1].strip() == last_line
    ]
    threshold = 0.50 if len(potential) == 1 else 0.70
    out: list[tuple[int, int]] = []
    for i in potential:
        if n <= 2:
            similarity = 1.0
        else:
            content_middle = "\n".join(norm_content_lines[i + 1 : i + n - 1])
            pattern_middle = "\n".join(pattern_lines[1:-1])
            similarity = SequenceMatcher(None, content_middle, pattern_middle).ratio()
        if similarity >= threshold:
            out.append(_calc_positions(orig_content_lines, i, i + n, len(content)))
    return out


def _strategy_context_aware(content: str, pattern: str) -> list[tuple[int, int]]:
    pattern_lines = pattern.split("\n")
    content_lines = content.split("\n")
    if not pattern_lines:
        return []
    n = len(pattern_lines)
    out: list[tuple[int, int]] = []
    for i in range(len(content_lines) - n + 1):
        block_lines = content_lines[i : i + n]
        high = sum(
            1
            for p, c in zip(pattern_lines, block_lines)
            if SequenceMatcher(None, p.strip(), c.strip()).ratio() >= 0.80
        )
        if high >= n * 0.5:
            out.append(_calc_positions(content_lines, i, i + n, len(content)))
    return out


def _map_normalized_positions(
    original: str, normalized: str, normalized_matches: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Best-effort map of match spans from a normalized string back to original.

    Walks both strings in lock-step, tolerating runs of collapsed whitespace.
    """
    if not normalized_matches:
        return []
    out: list[tuple[int, int]] = []
    for nstart, nend in normalized_matches:
        # Anchor by matching the trimmed first non-space token region.
        # Walk original and normalized together counting non-space chars.
        oi = ni = 0
        ostart = oend = None
        while oi < len(original) and ni < len(normalized):
            oc, nc = original[oi], normalized[ni]
            if ni == nstart and ostart is None:
                ostart = oi
            if ni == nend:
                oend = oi
                break
            if oc.isspace() and nc.isspace():
                # consume the whole whitespace run on each side
                while oi < len(original) and original[oi].isspace():
                    oi += 1
                while ni < len(normalized) and normalized[ni].isspace():
                    ni += 1
                continue
            oi += 1
            ni += 1
        if ostart is None:
            ostart = oi
        if oend is None:
            oend = oi
        out.append((ostart, oend))
    return out


def fuzzy_find_and_replace(
    content: str, old_string: str, new_string: str, replace_all: bool = False
) -> tuple[str, int, str, str | None]:
    """Find ``old_string`` and replace with ``new_string``.

    Returns (new_content, match_count, strategy_name, error_message).
    On success error_message is None. When multiple matches exist and
    replace_all is False, returns an "ambiguous" error so the caller can
    ask the model to add context.
    """
    if old_string == new_string:
        return content, 0, "", "old_string and new_string are identical"
    strategies = [
        ("exact", _strategy_exact),
        ("line_trimmed", _strategy_line_trimmed),
        ("whitespace_normalized", _strategy_whitespace_normalized),
        ("indentation_flexible", _strategy_indentation_flexible),
        ("escape_normalized", _strategy_escape_normalized),
        ("trimmed_boundary", _strategy_trimmed_boundary),
        ("unicode_normalized", _strategy_unicode_normalized),
        ("block_anchor", _strategy_block_anchor),
        ("context_aware", _strategy_context_aware),
    ]
    for name, fn in strategies:
        matches = fn(content, old_string)
        if not matches:
            continue
        # De-duplicate / sort spans.
        matches = sorted(set(matches))
        if len(matches) > 1 and not replace_all:
            return (
                content,
                len(matches),
                name,
                f"Found {len(matches)} matches for the given text. "
                "Add surrounding context to make it unique, or pass replace_all=true.",
            )
        # Apply replacements right-to-left so earlier offsets stay valid.
        new_content = content
        for start, end in sorted(matches, reverse=True):
            new_content = new_content[:start] + new_string + new_content[end:]
        return new_content, len(matches), name, None
    return content, 0, "", f"Could not find the text to replace in the file."


def find_closest_lines(old_string: str, content: str, context_lines: int = 2, max_results: int = 3) -> str:
    """Return a formatted "did you mean?" snippet of the closest lines."""
    if not old_string or not content:
        return ""
    old_lines = old_string.splitlines()
    content_lines = content.splitlines()
    if not old_lines or not content_lines:
        return ""
    anchor = old_lines[0].strip()
    if not anchor:
        candidates = [l.strip() for l in old_lines if l.strip()]
        if not candidates:
            return ""
        anchor = candidates[0]
    scored = []
    for i, line in enumerate(content_lines):
        stripped = line.strip()
        if not stripped:
            continue
        ratio = SequenceMatcher(None, anchor, stripped).ratio()
        if ratio > 0.3:
            scored.append((ratio, i))
    if not scored:
        return ""
    scored.sort(key=lambda x: -x[0])
    parts, seen = [], set()
    for _, idx in scored[:max_results]:
        start = max(0, idx - context_lines)
        end = min(len(content_lines), idx + len(old_lines) + context_lines)
        if (start, end) in seen:
            continue
        seen.add((start, end))
        parts.append(
            "\n".join(f"{start + j + 1:4d}| {content_lines[start + j]}" for j in range(end - start))
        )
    return "\n---\n".join(parts)
