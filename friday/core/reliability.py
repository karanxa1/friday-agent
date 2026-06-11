"""Reliability helpers: retry-with-backoff + a simple stall guard.

Used to wrap flaky external calls (LLM endpoint, MCP tools, HTTP). Kept small
and dependency-free. ADK already drives the tool loop; this protects the
*edges* (the calls that actually touch the network).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from core import audit

T = TypeVar("T")


def retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    label: str = "call",
) -> T:
    """Call ``func`` with exponential backoff. Re-raises after the last attempt."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return func()
        except exceptions as exc:  # noqa: PERF203
            last = exc
            delay = min(base_delay * (2**i), max_delay)
            audit.log("reliability.retry", label=label, attempt=i + 1, error=str(exc)[:200], delay=delay)
            if i < attempts - 1:
                time.sleep(delay)
    assert last is not None
    raise last


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    label: str = "call",
) -> T:
    """Async version of :func:`retry`."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return await func()
        except exceptions as exc:
            last = exc
            delay = min(base_delay * (2**i), max_delay)
            audit.log("reliability.retry", label=label, attempt=i + 1, error=str(exc)[:200], delay=delay)
            if i < attempts - 1:
                await asyncio.sleep(delay)
    assert last is not None
    raise last


async def with_deadline(coro: Awaitable[T], *, seconds: float, label: str = "task") -> T:
    """Run ``coro`` under a wall-clock deadline; raises TimeoutError if exceeded.

    This is the stall guard for multi-step agent runs.
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        audit.log("reliability.stall", label=label, seconds=seconds)
        raise TimeoutError(f"{label} exceeded {seconds}s deadline")
