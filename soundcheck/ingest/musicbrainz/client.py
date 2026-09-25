"""Async MusicBrainz client with strict 1 req/s, backoff, and disk caching."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path

import httpx
from pydantic import JsonValue, TypeAdapter, ValidationError

from soundcheck.ingest.http import (
    AsyncRateLimiter,
    DiskJsonCache,
    QueryValue,
    RateLimiter,
    Sleeper,
)

MUSICBRAINZ_API_ROOT = "https://musicbrainz.org/ws/2"
MUSICBRAINZ_USER_AGENT = "Soundcheck/0.1 ( contact-email )"
MUSICBRAINZ_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
MUSICBRAINZ_MAX_RETRY_DELAY_SECONDS = 60.0
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


def musicbrainz_user_agent(contact_email: str | None = None) -> str:
    """Build the required descriptive identity without logging the contact."""
    contact = (contact_email or os.environ.get("MUSICBRAINZ_CONTACT_EMAIL", "")).strip()
    if not contact:
        return MUSICBRAINZ_USER_AGENT
    if "\r" in contact or "\n" in contact:
        msg = "MusicBrainz contact email must be a single line"
        raise ValueError(msg)
    return f"Soundcheck/0.1 ( {contact} )"


class MusicBrainzClient:
    """Official unauthenticated MusicBrainz read client."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        limiter: RateLimiter | None = None,
        cache: DiskJsonCache | None = None,
        sleeper: Sleeper = asyncio.sleep,
        max_attempts: int = 8,
        user_agent: str = MUSICBRAINZ_USER_AGENT,
    ) -> None:
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)
        self._http_client = http_client
        self._limiter = limiter or AsyncRateLimiter(1.0)
        self._cache = cache or DiskJsonCache(
            Path(".cache/musicbrainz"),
            max_age_seconds=MUSICBRAINZ_CACHE_MAX_AGE_SECONDS,
        )
        self._sleeper = sleeper
        self._max_attempts = max_attempts
        self._user_agent = user_agent

    async def get(
        self,
        path: str,
        params: Mapping[str, QueryValue],
    ) -> dict[str, JsonValue]:
        """GET one API resource after enforcing cache, identity, and pacing."""
        normalized_path = path.strip("/")
        cached = await self._cache.get(normalized_path, params)
        if cached is not None:
            return _JSON_OBJECT.validate_json(cached)

        delay = 1.0
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.acquire()
            try:
                request_params = {
                    "fmt": "json",
                    **{key: str(value) for key, value in params.items()},
                }
                response = await self._http_client.get(
                    f"{MUSICBRAINZ_API_ROOT}/{normalized_path}",
                    params=httpx.QueryParams(request_params),
                    headers={"User-Agent": self._user_agent},
                )
                if response.status_code in _RETRYABLE_HTTP_STATUS:
                    response.raise_for_status()
                response.raise_for_status()
                payload = _JSON_OBJECT.validate_json(response.content)
            except (
                httpx.TransportError,
                httpx.HTTPStatusError,
                # An empty or truncated 200 body is as transient as a timeout.
                ValidationError,
            ):
                if attempt == self._max_attempts:
                    raise
                await self._sleeper(delay)
                delay = min(delay * 2, MUSICBRAINZ_MAX_RETRY_DELAY_SECONDS)
                continue

            await self._cache.set(normalized_path, params, response.content)
            return payload

        raise AssertionError("unreachable")
