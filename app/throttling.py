"""Concurrency controls for upstream Google requests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AsyncConcurrencyLimiter:
    """Small async semaphore wrapper for service-level throttling.

    Args:
        max_concurrency: Maximum concurrent operations allowed.
    """

    def __init__(self, max_concurrency: int) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Acquire one concurrency slot for an upstream operation.

        Yields:
            None while the caller owns the slot.
        """
        async with self._semaphore:
            yield

