"""In-process tool registry (inspired by Friday' ``tools/registry.py``).

Tools are plain Python callables grouped into *toolsets*. Agents request a
set of toolset names; the builder resolves them to the actual callables.

This registry is for **native** Python FunctionTools. MCP-provided tools are
handled separately by :mod:`control_plane.builder` via ADK's ``MCPToolset``.

A monotonically increasing ``generation`` counter lets cached agents know
when to rebuild after hot-reload.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from core import audit


@dataclass
class ToolEntry:
    name: str
    toolset: str
    func: Callable
    description: str = ""
    # If a tool needs an env var to function, the builder can warn when absent.
    requires_env: tuple[str, ...] = field(default_factory=tuple)


class ToolRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, ToolEntry] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    def register(
        self,
        func: Callable,
        *,
        toolset: str,
        name: str | None = None,
        description: str = "",
        requires_env: tuple[str, ...] = (),
        override: bool = False,
    ) -> Callable:
        """Register a callable as a tool. Returns the callable (decorator-friendly)."""
        tool_name = name or func.__name__
        with self._lock:
            existing = self._tools.get(tool_name)
            if existing and existing.toolset != toolset and not override:
                raise ValueError(
                    f"tool '{tool_name}' already registered in toolset "
                    f"'{existing.toolset}'; pass override=True to replace"
                )
            self._tools[tool_name] = ToolEntry(
                name=tool_name,
                toolset=toolset,
                func=func,
                description=description or (func.__doc__ or "").strip().split("\n")[0],
                requires_env=requires_env,
            )
            self._generation += 1
        return func

    def deregister(self, name: str) -> bool:
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                self._generation += 1
                return True
            return False

    def get(self, name: str) -> ToolEntry | None:
        with self._lock:
            return self._tools.get(name)

    def toolsets(self) -> set[str]:
        with self._lock:
            return {t.toolset for t in self._tools.values()}

    def list(self) -> list[ToolEntry]:
        with self._lock:
            return list(self._tools.values())

    def resolve(self, toolset_names: list[str]) -> list[Callable]:
        """Return the callables for the requested toolsets (order-stable)."""
        wanted = set(toolset_names)
        with self._lock:
            out = [t.func for t in self._tools.values() if t.toolset in wanted]
        audit.log("registry.resolve", toolsets=toolset_names, count=len(out))
        return out


# Module-level singleton (mirrors Friday).
registry = ToolRegistry()


def tool(toolset: str, *, name: str | None = None, description: str = "", requires_env: tuple[str, ...] = ()):
    """Decorator to register a function as a tool in ``toolset``."""

    def _wrap(func: Callable) -> Callable:
        registry.register(
            func,
            toolset=toolset,
            name=name,
            description=description,
            requires_env=requires_env,
        )
        return func

    return _wrap
