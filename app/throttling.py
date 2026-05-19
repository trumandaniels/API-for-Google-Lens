"""Concurrency controls for upstream Google requests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AsyncConcurrencyLimiter:
    """Small async semaphore wrapper for service-level throttling.

    Args:
        max_concurrency: Maximum concurrent operations allowed.

    Example:
        >>> limiter = AsyncConcurrencyLimiter(1)
        >>> hasattr(limiter, "slot")
        True
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

        Example:
            >>> import asyncio
            >>> async def use_slot():
            ...     limiter = AsyncConcurrencyLimiter(1)
            ...     async with limiter.slot():
            ...         return "acquired"
            >>> asyncio.run(use_slot())
            'acquired'
        """
        async with self._semaphore:
            yield

