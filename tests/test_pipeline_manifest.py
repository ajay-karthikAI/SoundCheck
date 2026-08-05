"""Durable pipeline-run manifest tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from soundcheck.scripts.pipeline_manifest import (
    begin_pipeline_run,
    finish_pipeline_run,
)
from soundcheck.sql.loader import load_sql

_STARTED_AT = datetime(2026, 7, 20, 5, tzinfo=UTC)
_OBSERVED_AT = _STARTED_AT + timedelta(minutes=2)
_COMPLETED_AT = _STARTED_AT + timedelta(minutes=5)


def test_pipeline_manifest_records_windowed_counts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "manifest.duckdb"
    begin_pipeline_run(
        database_path,
        run_id="run-42",
        run_kind="weekly",
        trigger_name="workflow_dispatch",
        git_sha="abc123",
        started_at=_STARTED_AT,
    )
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            load_sql("insert_raw_bluesky_posts.sql"),
            (
                "at://did:plc:test/app.bsky.feed.post/1",
                "did:plc:test",
                _OBSERVED_AT,
                "Listening to Slowdive",
                ["en"],
                [],
                [],
                ["intent:listening_to"],
                _OBSERVED_AT,
            ),
        )
        connection.execute(
            load_sql("insert_raw_bluesky_engagement.sql"),
            (
                "at://did:plc:test/app.bsky.feed.post/1",
                2,
                1,
                0,
                _OBSERVED_AT,
            ),
        )
        connection.execute(
            load_sql("insert_raw_lastfm_tag_snapshots.sql"),
            ("shoegaze", 10, 20, [], [], _OBSERVED_AT),
        )
        connection.execute(
            load_sql("insert_raw_lastfm_artist_snapshots.sql"),
            ("Slowdive", None, 10, 20, ["shoegaze"], ["shoegaze"], _OBSERVED_AT),
        )
        connection.execute(
            load_sql("insert_raw_mb_release_groups.sql"),
            (
                "00000000-0000-0000-0000-000000000001",
                "Everything Is Alive",
                [],
                [],
                date(2026, 7, 20).isoformat(),
                ["Album"],
                ["shoegaze"],
                [],
                _OBSERVED_AT,
            ),
        )
        connection.execute(
            load_sql("insert_stg_post_artist_attempts.sql"),
            (
                "at://did:plc:test/app.bsky.feed.post/1",
                "resolved",
                1,
                _OBSERVED_AT,
            ),
        )
        connection.execute(
            load_sql("upsert_stg_post_artist_links.sql"),
            (
                "at://did:plc:test/app.bsky.feed.post/1",
                None,
                "Slowdive",
                "lastfm_name",
                100.0,
                "name",
                _OBSERVED_AT,
            ),
        )

    counts = finish_pipeline_run(
        database_path,
        run_id="run-42",
        status="success",
        completed_at=_COMPLETED_AT,
    )

    assert counts.bluesky_posts_ingested == 1
    assert counts.bluesky_engagement_snapshots_ingested == 1
    assert counts.lastfm_tag_snapshots_ingested == 1
    assert counts.lastfm_artist_snapshots_ingested == 1
    assert counts.musicbrainz_release_groups_ingested == 1
    assert counts.resolution_posts_attempted == 1
    assert counts.resolution_links_resolved == 1
    assert counts.resolution_rate == 1.0
    assert counts.metric_rows == counts.forecast_rows == counts.brief_rows == 0
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            load_sql("select_pipeline_run.sql"),
            ("run-42",),
        ).fetchone()
    assert row is not None
    assert row[4] == "success"
    assert row[7] == pytest.approx(300.0)
    assert row[15] == pytest.approx(1.0)
    assert row[19] is None


def test_pipeline_manifest_rejects_unknown_run(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.duckdb"
    begin_pipeline_run(
        database_path,
        run_id="known",
        run_kind="daily",
        trigger_name="schedule",
        git_sha=None,
        started_at=_STARTED_AT,
    )

    with pytest.raises(ValueError, match="pipeline run not found"):
        finish_pipeline_run(
            database_path,
            run_id="unknown",
            status="failed",
            completed_at=_COMPLETED_AT,
        )
