"""P15: inline <thinking> tag normalization in the streaming bridge."""

from __future__ import annotations

from control_plane.streaming import _ThinkTagFilter


def _run(deltas: list[str]) -> list[tuple[bool, str]]:
    f = _ThinkTagFilter()
    out: list[tuple[bool, str]] = []
    for d in deltas:
        out.extend(f.feed(d))
    out.extend(f.flush())
    return out


def _join(segs: list[tuple[bool, str]], thought: bool) -> str:
    return "".join(t for is_th, t in segs if is_th == thought)


def test_plain_text_passes_through():
    segs = _run(["Hello ", "world"])
    assert segs == [(False, "Hello "), (False, "world")]


def test_whole_tags_in_one_delta():
    segs = _run(["<thinking>I ponder</thinking>The answer is 4."])
    assert _join(segs, True) == "I ponder"
    assert _join(segs, False) == "The answer is 4."


def test_tag_split_across_deltas():
    segs = _run(["<thin", "king>deep ", "thought</think", "ing>done"])
    assert _join(segs, True) == "deep thought"
    assert _join(segs, False) == "done"


def test_unclosed_thinking_stays_thought():
    segs = _run(["<thinking>never closed"])
    assert _join(segs, True) == "never closed"
    assert _join(segs, False) == ""


def test_partial_tag_prefix_flushed_as_text():
    # A lone "<thin" that never completes the tag is real text, not a thought.
    segs = _run(["a < b and <thin"])
    assert _join(segs, False) == "a < b and <thin"


def test_angle_brackets_in_answer_untouched():
    segs = _run(["use List<thing> generics"])
    assert _join(segs, False) == "use List<thing> generics"
    assert _join(segs, True) == ""
