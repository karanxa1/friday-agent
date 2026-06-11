"""Computer-use toolset: let the agent see and control the real desktop.

Gives the agent OS-level control via pyautogui — it can screenshot the screen,
move/click the mouse, type text, press keys and scroll. This is the most
powerful (and most dangerous) capability: it drives the actual machine, not a
sandbox. So every *control* action (click/type/key/scroll/move/drag) is routed
through the human-approval queue; only ``computer_screenshot`` and
``computer_screen_info`` run freely (read-only).

Inspired by the reference ``tools/computer_use_tool.py``.

macOS note: the first screenshot/click will require granting the host process
Screen Recording + Accessibility permission (System Settings → Privacy). Tools
return a clear message if permission is missing.
"""

from __future__ import annotations

import time
from typing import Any

from control_plane import approvals
from core import audit
from core.config import settings
from core.registry import tool

_MAX_TYPE = 5000
_PNG_PREFIX = "screen_"


def _images_dir():
    d = settings.home / "workspace" / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pg() -> Any:
    """Import pyautogui lazily (it opens a display connection on import)."""
    import pyautogui

    pyautogui.FAILSAFE = False  # don't abort if the cursor hits a corner
    return pyautogui


# ── read-only tools (no approval) ──────────────────────────────────────────


@tool("computer", description="Screenshot the whole desktop (saved to workspace; shown inline).")
def computer_screenshot() -> str:
    """Capture the current screen as a PNG and return its path.

    The image is saved under workspace/images and rendered inline in the UI so
    you (and the agent) can see the desktop before acting on it.
    """
    try:
        pg = _pg()
        path = _images_dir() / f"{_PNG_PREFIX}{int(time.time())}.png"
        img = pg.screenshot()
        img.save(str(path))
    except Exception as exc:  # noqa: BLE001
        return (
            f"error: screenshot failed: {str(exc)[:200]}. On macOS, grant the "
            f"host process Screen Recording permission (System Settings → "
            f"Privacy & Security → Screen Recording)."
        )
    audit.log("computer.screenshot", file=path.name)
    w, h = pg.size()
    return f"screenshot saved: {path}\nscreen size: {w}x{h}"


@tool("computer", description="Get the screen resolution and current mouse position.")
def computer_screen_info() -> str:
    """Return the screen size and the current mouse coordinates."""
    try:
        pg = _pg()
        w, h = pg.size()
        x, y = pg.position()
    except Exception as exc:  # noqa: BLE001
        return f"error: {str(exc)[:200]}"
    return f"screen: {w}x{h}\nmouse at: ({x}, {y})"


# ── control tools (approval-gated) ──────────────────────────────────────────
# These actually move the mouse / press keys on the host. They stage an
# approval; once approved, apply_computer_action performs the action.


@tool("computer", description="Move the mouse and click at screen coordinates (requires approval).")
def computer_click(x: int = -1, y: int = -1, button: str = "left", double: bool = False) -> str:
    """Stage a mouse click at absolute screen coordinates (x, y).

    Args:
        x: x pixel coordinate (from computer_screenshot / screen_info).
        y: y pixel coordinate.
        button: 'left', 'right', or 'middle'.
        double: double-click if true.
    """
    if x < 0 or y < 0:
        return "error: x and y are required (use computer_screenshot to locate targets)"
    if button not in ("left", "right", "middle"):
        return "error: button must be left, right, or middle"
    entry = approvals.submit(
        "computer",
        summary=f"{'double-' if double else ''}{button} click at ({x}, {y})",
        payload={"op": "click", "x": x, "y": y, "button": button, "double": double},
    )
    return f"staged computer action {entry['id']} (status={entry['status']}). Use apply_computer_action once approved."


@tool("computer", description="Type a string of text at the current focus (requires approval).")
def computer_type(text: str = "") -> str:
    """Stage typing ``text`` wherever the keyboard focus currently is.

    Args:
        text: the text to type (<=5000 chars).
    """
    if not text:
        return "error: text is required"
    if len(text) > _MAX_TYPE:
        return f"error: text too long (>{_MAX_TYPE} chars)"
    entry = approvals.submit(
        "computer",
        summary=f"type {len(text)} chars: {text[:60]!r}",
        payload={"op": "type", "text": text},
    )
    return f"staged computer action {entry['id']} (status={entry['status']}). Use apply_computer_action once approved."


@tool("computer", description="Press a key or hotkey combo, e.g. 'enter' or 'command+s' (requires approval).")
def computer_key(keys: str = "") -> str:
    """Stage a key press or chord.

    Args:
        keys: a single key ('enter', 'tab', 'esc') or a combo joined by '+'
            ('command+s', 'ctrl+c', 'command+shift+4').
    """
    if not keys:
        return "error: keys is required (e.g. 'enter' or 'command+s')"
    entry = approvals.submit(
        "computer",
        summary=f"press {keys}",
        payload={"op": "key", "keys": keys},
    )
    return f"staged computer action {entry['id']} (status={entry['status']}). Use apply_computer_action once approved."


@tool("computer", description="Scroll the mouse wheel up (+) or down (-) (requires approval).")
def computer_scroll(amount: int = 0) -> str:
    """Stage a scroll. Positive scrolls up, negative scrolls down.

    Args:
        amount: number of scroll 'clicks' (e.g. 5 up, -5 down).
    """
    if amount == 0:
        return "error: amount must be non-zero"
    entry = approvals.submit(
        "computer",
        summary=f"scroll {amount}",
        payload={"op": "scroll", "amount": amount},
    )
    return f"staged computer action {entry['id']} (status={entry['status']}). Use apply_computer_action once approved."


@tool("computer", description="Apply an approved computer action (click/type/key/scroll).")
def apply_computer_action(approval_id: str = "") -> str:
    """Perform a previously-staged, now-approved computer action.

    Args:
        approval_id: the id returned by a computer_* tool.
    """
    if not approval_id:
        return "error: approval_id is required"
    entry = approvals.get(approval_id)
    if entry is None:
        return f"error: no staged action {approval_id!r}"
    if entry.get("status") != "approved":
        return f"error: action {approval_id} is {entry.get('status')}, not approved"
    if entry.get("type") != "computer":
        return f"error: {approval_id} is not a computer action"
    payload = entry.get("payload") or {}
    op = payload.get("op")
    try:
        pg = _pg()
        if op == "click":
            pg.click(
                x=int(payload["x"]),
                y=int(payload["y"]),
                button=str(payload.get("button", "left")),
                clicks=2 if payload.get("double") else 1,
            )
        elif op == "type":
            pg.typewrite(str(payload["text"]), interval=0.01)
        elif op == "key":
            keys = [k.strip() for k in str(payload["keys"]).split("+") if k.strip()]
            if len(keys) == 1:
                pg.press(keys[0])
            else:
                pg.hotkey(*keys)
        elif op == "scroll":
            pg.scroll(int(payload["amount"]))
        else:
            return f"error: unknown op {op!r}"
    except Exception as exc:  # noqa: BLE001
        return (
            f"error: action failed: {str(exc)[:200]}. On macOS, grant the host "
            f"process Accessibility permission (System Settings → Privacy & "
            f"Security → Accessibility)."
        )
    approvals.mark_applied(approval_id)
    audit.log("computer.apply", op=op, approval_id=approval_id)
    return f"applied computer action {approval_id} ({op})"
