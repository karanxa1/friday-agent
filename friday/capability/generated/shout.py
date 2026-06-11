"""Agent-generated tool module: shout."""

from core.registry import tool


@tool('custom', description='Uppercase text.')
def shout(text: str) -> str:
    """Uppercase text."""
    return text.upper()
