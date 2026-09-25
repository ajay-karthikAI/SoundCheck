"""Offline cache, rate-limit, and official-client tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from soundcheck.ingest.http import AsyncRateLimiter, DiskJsonCache, QueryValue
from soundcheck.ingest.lastfm.client import LastfmClient
from soundcheck.ingest.musicbrainz.client import (
    MUSICBRAINZ_USER_AGENT,
    MusicBrainzClient,
)


class FakeTime:
    """Deterministic monotonic clock and async sleeper."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


class NoopLimiter:
    """Test limiter for client behavior unrelated to pacing."""

    async def acquire(self) -> None:
        return None


@pytest.mark.asyncio
async def test_rate_limiters_evenly_space_request_starts() -> None:
    lastfm_time = FakeTime()
    lastfm_limiter = AsyncRateLimiter(
        4.0,
        clock=lastfm_time.clock,
        sleeper=lastfm_time.sleep,
    )
    for _ in range(4):
        await lastfm_limiter.acquire()
    assert lastfm_time.sleeps == [0.25, 0.25, 0.25]

    musicbrainz_time = FakeTime()
    musicbrainz_limiter = AsyncRateLimiter(
        1.0,
        clock=musicbrainz_time.clock,
        sleeper=musicbrainz_time.sleep,
    )
    for _ in range(3):
        await musicbrainz_limiter.acquire()
    assert musicbrainz_time.sleeps == [1.0, 1.0]


@pytest.mark.asyncio
async def test_lastfm_cache_hides_key_and_avoids_duplicate_request(
    tmp_path: Path,
    lastfm_responses: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []
    secret = "super-secret-lastfm-key"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=lastfm_responses["tag.getInfo"])

    cache_directory = tmp_path / "lastfm"
    cache = DiskJsonCache(cache_directory, max_age_seconds=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = LastfmClient(
            http_client,
            secret,
            limiter=NoopLimiter(),
            cache=cache,
        )
        first = await client.get("tag.getInfo", {"tag": "shoegaze"})
        second = await client.get("tag.getInfo", {"tag": "shoegaze"})

    assert first == second
    assert len(requests) == 1
    assert requests[0].url.params["api_key"] == secret
    assert len(list(cache_directory.glob("*.json"))) == 1
    assert all(secret not in path.name for path in cache_directory.iterdir())
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_clients_exponentially_back_off_and_musicbrainz_identifies(
    tmp_path: Path,
) -> None:
    lastfm_delays: list[float] = []
    lastfm_attempts = 0

    async def lastfm_sleep(delay: float) -> None:
        lastfm_delays.append(delay)

    def lastfm_handler(request: httpx.Request) -> httpx.Response:
        nonlocal lastfm_attempts
        lastfm_attempts += 1
        if lastfm_attempts < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"tag": {"name": "x", "reach": 1, "total": 2}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lastfm_handler)
    ) as http_client:
        lastfm = LastfmClient(
            http_client,
            "test-key",
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "lfm", max_age_seconds=None),
            sleeper=lastfm_sleep,
            max_attempts=3,
        )
        await lastfm.get("tag.getInfo", {"tag": "x"})
    assert lastfm_delays == [1.0, 2.0]

    musicbrainz_requests: list[httpx.Request] = []

    def musicbrainz_handler(request: httpx.Request) -> httpx.Response:
        musicbrainz_requests.append(request)
        return httpx.Response(200, json={"count": 0, "offset": 0, "release-groups": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(musicbrainz_handler)
    ) as http_client:
        musicbrainz = MusicBrainzClient(
            http_client,
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "mb", max_age_seconds=None),
        )
        params: dict[str, QueryValue] = {
            "query": "firstreleasedate:2026",
            "limit": 100,
            "offset": 0,
        }
        await musicbrainz.get("release-group", params)
        await musicbrainz.get("release-group", params)

    assert len(musicbrainz_requests) == 1
    assert musicbrainz_requests[0].headers["User-Agent"] == MUSICBRAINZ_USER_AGENT


@pytest.mark.asyncio
async def test_clients_retry_empty_success_bodies(tmp_path: Path) -> None:
    attempts: dict[str, int] = {}
    delays: list[float] = []

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        attempts[host] = attempts.get(host, 0) + 1
        if attempts[host] == 1:
            return httpx.Response(200, content=b"")
        return httpx.Response(200, json={"ok": True})

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(flaky_handler)
    ) as http_client:
        lastfm = LastfmClient(
            http_client,
            "test-key",
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "lfm", max_age_seconds=None),
            sleeper=record_sleep,
        )
        musicbrainz = MusicBrainzClient(
            http_client,
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "mb", max_age_seconds=None),
            sleeper=record_sleep,
        )
        assert await lastfm.get("artist.getInfo", {"artist": "x"}) == {"ok": True}
        assert await musicbrainz.get("artist", {"query": "x"}) == {"ok": True}

    assert attempts == {"ws.audioscrobbler.com": 2, "musicbrainz.org": 2}
    assert delays == [1.0, 1.0]

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(empty_handler)
    ) as http_client:
        lastfm = LastfmClient(
            http_client,
            "test-key",
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "lfm-empty", max_age_seconds=None),
            sleeper=record_sleep,
            max_attempts=2,
        )
        with pytest.raises(ValidationError):
            await lastfm.get("artist.getInfo", {"artist": "x"})
