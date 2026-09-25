"""Offline Jetstream processing and DuckDB batching tests."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from websockets.exceptions import InvalidMessage

from soundcheck.ingest.bluesky.jetstream import (
    _RETRYABLE_CONNECTION_ERRORS,
    JetstreamIngestor,
    _jetstream_url,
)
from soundcheck.ingest.bluesky.models import RawBlueskyPost
from soundcheck.ingest.bluesky.storage import PostBatchWriter
from soundcheck.sql.loader import load_sql


def _post(number: int) -> RawBlueskyPost:
    return RawBlueskyPost(
        uri=f"at://did:plc:test/app.bsky.feed.post/{number}",
        did="did:plc:test",
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
        text="new album",
        langs=("en",),
        link_urls=(),
        hashtags=(),
        matched_rules=("intent:new_album",),
        ingested_at=datetime(2026, 7, 20, 1, tzinfo=UTC),
    )


def _row_count(database_path: Path) -> int:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(load_sql("count_raw_bluesky_posts.sql")).fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_writer_inserts_exact_batches_of_100(tmp_path: Path) -> None:
    database_path = tmp_path / "batch.duckdb"
    writer = PostBatchWriter(database_path)
    await writer.initialize()

    for number in range(99):
        assert await writer.add(_post(number)) == 0
    assert _row_count(database_path) == 0

    assert await writer.add(_post(99)) == 100
    assert _row_count(database_path) == 100


@pytest.mark.asyncio
async def test_ingestor_classifies_writes_utc_and_logs_counters(
    tmp_path: Path,
    jetstream_message: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database_path = tmp_path / "ingest.duckdb"
    writer = PostBatchWriter(database_path)
    await writer.initialize()
    logger = logging.getLogger("test.jetstream")
    ingestor = JetstreamIngestor(writer, logger)

    with caplog.at_level(logging.INFO, logger="test.jetstream"):
        await ingestor.process_message(jetstream_message)
        assert ingestor.counters.seen == 1
        assert ingestor.counters.matched == 1
        assert ingestor.counters.written == 0
        assert await ingestor.flush() == 1

    assert ingestor.counters.written == 1
    assert await writer.latest_cursor() == 1784552400000000
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(load_sql("select_raw_bluesky_post_evidence.sql")).fetchone()
    assert row is not None
    assert row[0] == "at://did:plc:exampleartist/app.bsky.feed.post/3lexample"
    assert row[1].astimezone(UTC) == datetime(2026, 7, 20, 18, tzinfo=UTC)
    assert set(row[2]) == {
        "hashtag:#newrelease",
        "intent:new_ep",
        "intent:just_dropped",
        "link:open.spotify.com",
    }
    assert row[3] == ["NewRelease"]
    assert row[4] == ["https://open.spotify.com/album/example"]

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "final_batch_written"
    assert payload["seen"] == 1
    assert payload["matched"] == 1
    assert payload["written"] == 1


def _commit_message(record: Mapping[str, object], time_us: int) -> str:
    return json.dumps(
        {
            "did": "did:plc:test",
            "time_us": time_us,
            "kind": "commit",
            "commit": {
                "operation": "create",
                "collection": "app.bsky.feed.post",
                "rkey": str(time_us),
                "record": record,
            },
        }
    )


@pytest.mark.asyncio
async def test_ingestor_survives_malformed_public_records(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    writer = PostBatchWriter(tmp_path / "malformed.duckdb")
    await writer.initialize()
    logger = logging.getLogger("test.jetstream.malformed")
    ingestor = JetstreamIngestor(writer, logger)
    unparseable_link = {
        "text": "#nowplaying",
        "createdAt": "2026-07-20T12:00:00Z",
        "facets": [
            {
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": "https://NHL.com]",
                    }
                ]
            }
        ],
    }
    overflowing_timestamp = {
        "text": "#nowplaying",
        "createdAt": "0001-01-01T00:00:00+05:00",
    }

    with caplog.at_level(logging.INFO, logger="test.jetstream.malformed"):
        await ingestor.process_message(_commit_message(unparseable_link, 1))
        await ingestor.process_message(_commit_message(overflowing_timestamp, 2))

    assert ingestor.counters.seen == 2
    assert ingestor.counters.matched == 1
    assert json.loads(caplog.records[-1].message)["event"] == "invalid_post"
    assert await ingestor.flush() == 1
    assert await writer.latest_cursor() == 2


def test_resume_url_advances_persisted_microsecond_cursor() -> None:
    assert _jetstream_url(None).endswith(
        "wantedCollections=app.bsky.feed.post"
    )
    assert _jetstream_url(1784552400000000).endswith(
        "cursor=1784552400000001"
    )


def test_invalid_handshake_response_is_retryable() -> None:
    error = InvalidMessage(
        "unsupported protocol; expected HTTP/1.1: HTTP/1.0 503"
    )
    assert isinstance(error, _RETRYABLE_CONNECTION_ERRORS)
