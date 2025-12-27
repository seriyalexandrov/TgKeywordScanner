"""Utility helpers."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

from telethon.errors import FloodWaitError, RPCError

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
S = TypeVar("S")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hours_ago(hours: int) -> datetime:
    return utc_now() - timedelta(hours=hours)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_exceptions: Iterable[type[BaseException]] = (FloodWaitError, RPCError),
) -> T:
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except tuple(retry_exceptions) as exc:
            if attempt >= max_attempts:
                raise
            delay = _compute_delay(base_delay, max_delay, attempt, exc)
            LOGGER.warning("Retrying after error: %s (attempt %s/%s)", exc.__class__.__name__, attempt, max_attempts)
            await asyncio.sleep(delay)


def _compute_delay(base_delay: float, max_delay: float, attempt: int, exc: BaseException) -> float:
    if isinstance(exc, FloodWaitError):
        wait_seconds = getattr(exc, "seconds", None)
        if isinstance(wait_seconds, int) and wait_seconds > 0:
            return min(wait_seconds, max_delay)
    exp_delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0.0, exp_delay / 4)
    return exp_delay + jitter


async def run_isolated_async(
    source_key: S,
    operation: Callable[[], Awaitable[T]],
    on_error: Callable[[S, Exception], None],
) -> Optional[T]:
    try:
        return await operation()
    except Exception as exc:
        on_error(source_key, exc)
        return None
