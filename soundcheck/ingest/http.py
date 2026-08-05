"""Shared async rate limiting and content-addressed disk caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Protocol

type QueryValue = str | int | float | bool
type Clock = Callable[[], float]
type Sleeper = Callable[[float], Awaitable[None]]


class RateLimiter(Protocol):
    """Structural interface accepted by official-API clients."""

    async def acquire(self) -> None:
        """Wait until one request may start."""
        ...


class AsyncRateLimiter:
    """Evenly space requests to enforce a strict maximum start rate."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        if requests_per_second <= 0:
            msg = "requests_per_second must be positive"
            raise ValueError(msg)
        self._interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleeper = sleeper
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait for the next request slot."""
        async with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_start - now)
            if delay:
                await self._sleeper(delay)
                now = self._clock()
            self._next_start = max(now, self._next_start) + self._interval


class DiskJsonCache:
    """Store validated API response bytes under deterministic SHA-256 keys."""

    def __init__(
        self,
        directory: Path,
        *,
        max_age_seconds: float | None,
        wall_clock: Clock = time.time,
    ) -> None:
        if max_age_seconds is not None and max_age_seconds < 0:
            msg = "max_age_seconds cannot be negative"
            raise ValueError(msg)
        self._directory = directory
        self._max_age_seconds = max_age_seconds
        self._wall_clock = wall_clock
        self._lock = asyncio.Lock()

    @staticmethod
    def key(method: str, params: Mapping[str, QueryValue]) -> str:
        """Hash a canonical representation of method and public parameters."""
        canonical = json.dumps(
            {"method": method, "params": sorted(params.items())},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    async def get(self, method: str, params: Mapping[str, QueryValue]) -> bytes | None:
        """Return fresh cached bytes, if present."""
        path = self._path(method, params)
        async with self._lock:
            return await asyncio.to_thread(self._read_fresh, path)

    async def set(
        self,
        method: str,
        params: Mapping[str, QueryValue],
        content: bytes,
    ) -> None:
        """Atomically persist response bytes."""
        path = self._path(method, params)
        async with self._lock:
            await asyncio.to_thread(self._write_atomic, path, content)

    def _path(self, method: str, params: Mapping[str, QueryValue]) -> Path:
        return self._directory / f"{self.key(method, params)}.json"

    def _read_fresh(self, path: Path) -> bytes | None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        if (
            self._max_age_seconds is not None
            and self._wall_clock() - stat.st_mtime > self._max_age_seconds
        ):
            return None
        return path.read_bytes()

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
