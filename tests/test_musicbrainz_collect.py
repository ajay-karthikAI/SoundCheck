"""Fixture-only MusicBrainz supply collection tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest

from soundcheck.ingest.http import DiskJsonCache
from soundcheck.ingest.musicbrainz.client import (
    MUSICBRAINZ_USER_AGENT,
    MusicBrainzClient,
    musicbrainz_user_agent,
)
from soundcheck.ingest.musicbrainz.collect import (
    RELEASE_GROUP_INCLUDES,
    build_release_group_query,
    collect_release_groups,
    incremental_window,
)
from soundcheck.ingest.musicbrainz.storage import MusicBrainzReleaseGroupWriter
from soundcheck.sql.loader import load_sql


class NoopLimiter:
    async def acquire(self) -> None:
        return None


def test_incremental_window_is_14_inclusive_days() -> None:
    assert incremental_window(date(2026, 7, 23)) == (
        date(2026, 7, 10),
        date(2026, 7, 23),
    )


def test_musicbrainz_user_agent_uses_explicit_contact() -> None:
    assert (
        musicbrainz_user_agent("ops@example.com")
        == "Soundcheck/0.1 ( ops@example.com )"
    )


def test_query_uses_date_window_and_shared_genres() -> None:
    query = build_release_group_query(
        date(2026, 7, 1),
        date(2026, 7, 31),
        ("shoegaze", "dnb"),
    )

    assert "firstreleasedate:[2026-07-01 TO 2026-07-31]" in query
    assert 'tag:"shoegaze"' in query
    assert 'tag:"dnb"' in query


@pytest.mark.asyncio
async def test_paginated_collection_is_insert_on_first_sight(
    tmp_path: Path,
    musicbrainz_pages: dict[str, Any],
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        offset = request.url.params["offset"]
        return httpx.Response(200, json=musicbrainz_pages[offset])

    database_path = tmp_path / "musicbrainz.duckdb"
    writer = MusicBrainzReleaseGroupWriter(database_path)
    cache = DiskJsonCache(tmp_path / "cache", max_age_seconds=None)
    fetched_at = datetime(2026, 7, 23, 12, tzinfo=UTC)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = MusicBrainzClient(
            http_client,
            limiter=NoopLimiter(),
            cache=cache,
        )
        for _ in range(2):
            assert await collect_release_groups(
                ("shoegaze", "dnb"),
                date(2026, 7, 10),
                date(2026, 7, 23),
                client,
                writer,
                fetched_at=fetched_at,
            ) == 2

    assert len(requests) == 2
    assert all(request.headers["User-Agent"] == MUSICBRAINZ_USER_AGENT for request in requests)
    assert all(request.url.params["inc"] == RELEASE_GROUP_INCLUDES for request in requests)
    assert [request.url.params["offset"] for request in requests] == ["0", "1"]

    with duckdb.connect(str(database_path), read_only=True) as connection:
        count = connection.execute(
            load_sql("summarize_raw_mb_release_groups.sql")
        ).fetchone()
        evidence = connection.execute(
            load_sql("select_raw_mb_release_group_evidence.sql")
        ).fetchall()

    assert count == (2,)
    assert evidence[0][0] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert evidence[0][1] == "First Supply Record"
    assert evidence[0][3] == ["cccccccc-cccc-cccc-cccc-cccccccccccc"]
    assert evidence[0][4] == "2026-07-20"
    assert evidence[0][5] == ["Album"]
    assert evidence[0][6] == ["shoegaze"]
    assert evidence[0][7] == [{"name": "shoegaze", "count": 8}, {"name": "dream pop", "count": 3}]
