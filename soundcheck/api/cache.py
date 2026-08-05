"""Small per-worker 60-second response cache."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    value: object


class TTLResponseCache:
    """Thread-safe bounded-by-time cache for immutable Pydantic responses."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        if ttl_seconds <= 0:
            msg = "cache TTL must be positive"
            raise ValueError(msg)
        self.ttl_seconds = ttl_seconds
        self._entries: dict[Hashable, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get_or_set[T](
        self,
        key: Hashable,
        factory: Callable[[], T],
    ) -> T:
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached.expires_at > now:
                return cast(T, cached.value)
        value = factory()
        with self._lock:
            self._entries[key] = _CacheEntry(
                expires_at=now + self.ttl_seconds,
                value=value,
            )
            expired = [
                cache_key
                for cache_key, entry in self._entries.items()
                if entry.expires_at <= now
            ]
            for cache_key in expired:
                self._entries.pop(cache_key, None)
        return value
