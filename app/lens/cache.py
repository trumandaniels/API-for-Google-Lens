"""In-process cache for successful Google Lens Exact Match responses."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import time

from app.models import ExactMatchHtml


@dataclass(frozen=True)
class ExactMatchCacheEntry:
    """Cached Exact Match HTML plus the monotonic time it was stored.

    Attributes:
        value: Classified Exact Match response safe to return as a `200`.
        stored_at: Monotonic timestamp used for TTL expiration.
    """

    value: ExactMatchHtml
    stored_at: float


class ExactMatchResponseCache:
    """Async TTL/LRU cache for valid Exact Match HTML.

    Args:
        max_entries: Maximum number of successful image URL responses to keep.
            A value less than one disables caching.
        ttl_seconds: Maximum cache age in seconds. A value less than or equal to
            zero disables caching.
        clock: Monotonic clock used by tests to make expiration deterministic.

    Notes:
        The cache stores only responses that already passed service
        classification as Exact Match HTML. Upstream errors, CAPTCHA pages,
        Google error pages, and unrecognized HTML are never cached.
    """

    def __init__(
        self,
        max_entries: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, ExactMatchCacheEntry] = OrderedDict()
        self._in_flight: dict[str, asyncio.Task[ExactMatchHtml]] = {}
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """Return whether this cache should store responses."""
        return self.max_entries > 0 and self.ttl_seconds > 0

    async def get_or_create(
        self,
        key: str,
        factory: Callable[[], Awaitable[ExactMatchHtml]],
    ) -> ExactMatchHtml:
        """Return a cached value or create it with a single shared task.

        Args:
            key: Stable cache key, usually the normalized public image URL.
            factory: Coroutine factory that fetches and classifies the response
                when the cache does not contain a fresh value.

        Returns:
            Cached or freshly fetched Exact Match HTML.

        Raises:
            Any exception raised by `factory`; failed fetches are not cached.
        """
        if not self.enabled:
            return await factory()

        async with self._lock:
            cached = self._get_fresh_locked(key)
            if cached is not None:
                return cached

            task = self._in_flight.get(key)
            if task is None:
                task = asyncio.create_task(factory())
                self._in_flight[key] = task

        try:
            result = await asyncio.shield(task)
        except Exception:
            async with self._lock:
                if self._in_flight.get(key) is task:
                    self._in_flight.pop(key, None)
            raise

        async with self._lock:
            if self._in_flight.get(key) is task:
                self._in_flight.pop(key, None)
            self._store_locked(key, result)

        return result

    def _get_fresh_locked(self, key: str) -> ExactMatchHtml | None:
        """Return a fresh cached value while the caller owns `_lock`."""
        entry = self._entries.get(key)
        if entry is None:
            return None

        if self._clock() - entry.stored_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None

        self._entries.move_to_end(key)
        return entry.value

    def _store_locked(self, key: str, value: ExactMatchHtml) -> None:
        """Store a value and prune old entries while the caller owns `_lock`."""
        self._entries[key] = ExactMatchCacheEntry(value=value, stored_at=self._clock())
        self._entries.move_to_end(key)

        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
