"""Async Last.fm client with enforced 4 req/s, backoff, and disk caching."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import httpx
from pydantic import JsonValue, TypeAdapter

from soundcheck.ingest.http import (
    AsyncRateLimiter,
    DiskJsonCache,
    QueryValue,
    RateLimiter,
    Sleeper,
)

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_CACHE_MAX_AGE_SECONDS = 6 * 60 * 60
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_RETRYABLE_API_ERRORS = frozenset({11, 16, 29})
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


class LastfmApiError(RuntimeError):
    """A sanitized Last.fm error that never includes request credentials."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(f"Last.fm API error {code}: {message}")


class LastfmClient:
    """Official Last.fm read client."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        *,
        limiter: RateLimiter | None = None,
        cache: DiskJsonCache | None = None,
        sleeper: Sleeper = asyncio.sleep,
        max_attempts: int = 4,
    ) -> None:
        if not api_key:
            msg = "LASTFM_API_KEY is required"
            raise ValueError(msg)
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)
        self._http_client = http_client
        self._api_key = api_key
        self._limiter = limiter or AsyncRateLimiter(4.0)
        self._cache = cache or DiskJsonCache(
            Path(".cache/lastfm"),
            max_age_seconds=LASTFM_CACHE_MAX_AGE_SECONDS,
        )
        self._sleeper = sleeper
        self._max_attempts = max_attempts

    @classmethod
    def from_env(
        cls,
        http_client: httpx.AsyncClient,
        *,
        cache_directory: Path = Path(".cache/lastfm"),
    ) -> LastfmClient:
        """Build a client without ever emitting the environment credential."""
        api_key = os.environ.get("LASTFM_API_KEY", "")
        cache = DiskJsonCache(
            cache_directory,
            max_age_seconds=LASTFM_CACHE_MAX_AGE_SECONDS,
        )
        return cls(http_client, api_key, cache=cache)

    async def get(
        self,
        method: str,
        params: Mapping[str, QueryValue],
    ) -> dict[str, JsonValue]:
        """Call one official method, using only public parameters in the cache key."""
        cached = await self._cache.get(method, params)
        if cached is not None:
            return _JSON_OBJECT.validate_json(cached)

        delay = 1.0
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.acquire()
            try:
                request_params = {
                    "method": method,
                    "api_key": self._api_key,
                    "format": "json",
                    **{key: str(value) for key, value in params.items()},
                }
                response = await self._http_client.get(
                    LASTFM_API_URL,
                    params=httpx.QueryParams(request_params),
                )
                if response.status_code in _RETRYABLE_HTTP_STATUS:
                    response.raise_for_status()
                response.raise_for_status()
                payload = _JSON_OBJECT.validate_json(response.content)
                api_error = _api_error(payload)
                if api_error is not None:
                    if api_error.code in _RETRYABLE_API_ERRORS:
                        raise _RetryableLastfmError(api_error)
                    raise api_error
            except (httpx.TransportError, httpx.HTTPStatusError, _RetryableLastfmError):
                if attempt == self._max_attempts:
                    raise
                await self._sleeper(delay)
                delay *= 2
                continue

            await self._cache.set(method, params, response.content)
            return payload

        raise AssertionError("unreachable")


class _RetryableLastfmError(RuntimeError):
    def __init__(self, error: LastfmApiError) -> None:
        self.error = error
        super().__init__(str(error))


def _api_error(payload: Mapping[str, JsonValue]) -> LastfmApiError | None:
    raw_code = payload.get("error")
    if raw_code is None:
        return None
    if isinstance(raw_code, str | int | float):
        try:
            code = int(raw_code)
        except ValueError:
            code = -1
    else:
        code = -1
    raw_message = payload.get("message", "unknown error")
    message = raw_message if isinstance(raw_message, str) else "unknown error"
    return LastfmApiError(code, message)
