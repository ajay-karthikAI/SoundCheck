"""Fixture-only Last.fm snapshot collection tests."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest

from soundcheck.ingest.http import DiskJsonCache
from soundcheck.ingest.lastfm.client import LastfmClient
from soundcheck.ingest.lastfm.collect import collect_lastfm
from soundcheck.ingest.lastfm.models import TagGetTopAlbumsResponse
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.sql.loader import load_sql


class NoopLimiter:
    async def acquire(self) -> None:
        return None


def test_top_albums_accepts_live_and_legacy_envelopes(
    lastfm_responses: dict[str, Any],
) -> None:
    live_payload = lastfm_responses["tag.getTopAlbums"]
    live_response = TagGetTopAlbumsResponse.model_validate(live_payload)
    legacy_response = TagGetTopAlbumsResponse.model_validate(
        {"topalbums": live_payload["albums"]}
    )

    assert live_response == legacy_response
    assert live_response.topalbums.album[0].name == "Cloud Record"


@pytest.mark.asyncio
async def test_two_runs_append_lifetime_totals_without_making_metrics(
    tmp_path: Path,
    lastfm_responses: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        method = request.url.params["method"]
        if method == "artist.getInfo":
            identity = request.url.params.get("mbid") or request.url.params["artist"]
            payload = lastfm_responses[method][identity]
        else:
            payload = lastfm_responses[method]
        return httpx.Response(200, json=payload)

    database_path = tmp_path / "lastfm.duckdb"
    writer = LastfmSnapshotWriter(database_path)
    cache = DiskJsonCache(tmp_path / "cache", max_age_seconds=None)
    first_poll = datetime(2026, 7, 20, 12, tzinfo=UTC)
    second_poll = datetime(2026, 7, 27, 12, tzinfo=UTC)
    logger = logging.getLogger("tests.lastfm.progress")

    with caplog.at_level(logging.INFO, logger=logger.name):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = LastfmClient(
                http_client,
                "fixture-key",
                limiter=NoopLimiter(),
                cache=cache,
            )
            assert await collect_lastfm(
                ("shoegaze",),
                client,
                writer,
                fetched_at=first_poll,
                logger=logger,
            ) == (1, 2)
            assert await collect_lastfm(
                ("shoegaze",),
                client,
                writer,
                fetched_at=second_poll,
                logger=logger,
            ) == (1, 2)

    assert request_count == 5
    progress_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == logger.name
    ]
    assert any(
        event["event"] == "lastfm_genre_progress" for event in progress_events
    )
    artist_progress = [
        event
        for event in progress_events
        if event["event"] == "lastfm_artist_progress"
    ]
    assert artist_progress[-1] == {
        "artist_snapshots_ready": 2,
        "artists_completed": 2,
        "artists_skipped": 0,
        "artists_total": 2,
        "event": "lastfm_artist_progress",
    }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        summary = connection.execute(
            load_sql("summarize_raw_lastfm_snapshots.sql")
        ).fetchone()
        artists = connection.execute(
            load_sql("select_raw_lastfm_artist_evidence.sql")
        ).fetchall()
        metric_table_count = connection.execute(
            load_sql("count_metric_tables.sql")
        ).fetchone()

    assert summary == (2, 4, 2)
    assert metric_table_count == (0,)
    example_snapshots = [row for row in artists if row[0] == "Example Gaze"]
    assert len(example_snapshots) == 2
    assert [row[3] for row in example_snapshots] == [87000, 87000]
    assert [row[6].astimezone(UTC) for row in example_snapshots] == [
        first_poll,
        second_poll,
    ]


@pytest.mark.asyncio
async def test_missing_artist_is_logged_and_does_not_abort_snapshot(
    tmp_path: Path,
    lastfm_responses: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.params["method"]
        if method != "artist.getInfo":
            return httpx.Response(200, json=lastfm_responses[method])
        identity = request.url.params.get("mbid") or request.url.params["artist"]
        if identity == "Second Artist":
            return httpx.Response(
                200,
                json={"error": 6, "message": "The artist could not be found"},
            )
        return httpx.Response(200, json=lastfm_responses[method][identity])

    database_path = tmp_path / "missing-artist.duckdb"
    writer = LastfmSnapshotWriter(database_path)
    logger = logging.getLogger("tests.lastfm.missing_artist")

    with caplog.at_level(logging.INFO, logger=logger.name):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = LastfmClient(
                http_client,
                "fixture-key",
                limiter=NoopLimiter(),
                cache=DiskJsonCache(tmp_path / "cache", max_age_seconds=None),
            )
            assert await collect_lastfm(
                ("shoegaze",),
                client,
                writer,
                fetched_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
                logger=logger,
            ) == (1, 1)

    progress_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == logger.name
    ]
    assert {
        "artist_name": "Second Artist",
        "error_code": 6,
        "event": "lastfm_artist_skipped",
        "lookup_type": "name",
    } in progress_events
    assert progress_events[-1] == {
        "artist_snapshots_ready": 1,
        "artists_completed": 2,
        "artists_skipped": 1,
        "artists_total": 2,
        "event": "lastfm_artist_phase_complete",
    }
    with duckdb.connect(str(database_path), read_only=True) as connection:
        summary = connection.execute(
            load_sql("summarize_raw_lastfm_snapshots.sql")
        ).fetchone()
    assert summary == (1, 1, 1)
