"""P21: computer-use toolset — registration, gating, screenshot, apply flow."""

from __future__ import annotations

import json

from control_plane import builder


def test_computer_tools_registered():
    builder.import_tool_modules()
    from core.registry import registry

    names = {e.name for e in registry.list() if e.toolset == "computer"}
    assert {
        "computer_screenshot",
        "computer_screen_info",
        "computer_click",
        "computer_type",
        "computer_key",
        "computer_scroll",
        "apply_computer_action",
    } <= names


def test_control_actions_are_gated():
    """Click/type/key/scroll must stage an approval, not act immediately."""
    from friday_tools import computer

    out = computer.computer_click(100, 200)
    assert "staged computer action" in out
    out = computer.computer_type("hello")
    assert "staged computer action" in out
    out = computer.computer_key("enter")
    assert "staged computer action" in out
    out = computer.computer_scroll(5)
    assert "staged computer action" in out


def test_control_actions_validate_args():
    from friday_tools import computer

    assert "x and y are required" in computer.computer_click()
    assert "text is required" in computer.computer_type("")
    assert "keys is required" in computer.computer_key("")
    assert "non-zero" in computer.computer_scroll(0)


def test_apply_rejects_unapproved():
    from friday_tools import computer

    # Stage a click (gated → pending), then try to apply without approval.
    staged = computer.computer_click(10, 20)
    # extract the id
    import re

    m = re.search(r"staged computer action (\S+)", staged)
    assert m
    aid = m.group(1)
    out = computer.apply_computer_action(aid)
    # At autonomy L1 it's pending, so apply must refuse.
    assert "not approved" in out or "is pending" in out


def test_apply_requires_id():
    from friday_tools import computer

    assert "approval_id is required" in computer.apply_computer_action("")


def test_screen_info_runs():
    """screen_info is read-only and should return size + mouse, or a clear error."""
    from friday_tools import computer

    out = computer.computer_screen_info()
    assert "screen:" in out or out.startswith("error:")
