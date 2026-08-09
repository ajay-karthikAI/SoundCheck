"""Fixture-only end-to-end tests for evidence-linked weekly marts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from soundcheck.metrics.maturity import SupplyCollectionWindow
from soundcheck.metrics.pipeline import build_metrics
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.sql.loader import load_sql


@pytest.mark.asyncio
async def test_metrics_pipeline_persists_deltas_indices_and_receipts(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "metrics.duckdb"
    store = DuckDBMetricStore(database_path)
    await store.initialize()
    first_snapshot = datetime(2026, 7, 6, 12, tzinfo=UTC)
    second_snapshot = datetime(2026, 7, 13, 12, tzinfo=UTC)
    post_time = datetime(2026, 7, 15, 9, tzinfo=UTC)
    genres = ("shoegaze", "ambient", "other")

    with duckdb.connect(str(database_path)) as connection:
        connection.executemany(
            load_sql("insert_raw_lastfm_artist_snapshots.sql"),
            [
                (
                    "Artist A",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    100,
                    1_000,
                    ["shoegaze"],
                    ["shoegaze"],
                    first_snapshot,
                ),
                (
                    "Artist A",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    110,
                    1_050,
                    ["shoegaze"],
                    ["shoegaze"],
                    second_snapshot,
                ),
                (
                    "Artist B",
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    200,
                    2_000,
                    ["ambient"],
                    ["ambient"],
                    first_snapshot,
                ),
                (
                    "Artist B",
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    201,
                    2_010,
                    ["ambient"],
                    ["ambient"],
                    second_snapshot,
                ),
            ],
        )
        connection.executemany(
            load_sql("insert_raw_bluesky_posts.sql"),
            [
                (
                    "at://post/a",
                    "did:plc:a",
                    post_time,
                    "Listening to Artist A",
                    ["en"],
                    [],
                    [],
                    ["intent:listening_to"],
                    post_time,
                ),
                (
                    "at://post/b",
                    "did:plc:b",
                    post_time,
                    "Listening to Artist B",
                    ["en"],
                    [],
                    [],
                    ["intent:listening_to"],
                    post_time,
                ),
                (
                    "at://post/not-music",
                    "did:plc:not-music",
                    post_time,
                    "A history documentary is now on YouTube",
                    ["en"],
                    ["https://youtube.com/watch?v=history"],
                    [],
                    ["link:youtube.com"],
                    post_time,
                ),
            ],
        )
        connection.executemany(
            load_sql("insert_raw_bluesky_engagement.sql"),
            [
                    ("at://post/a", 4, 2, 1, post_time + timedelta(hours=72)),
                    ("at://post/b", 0, 0, 0, post_time + timedelta(hours=72)),
            ],
        )
        connection.executemany(
            load_sql("upsert_stg_post_artist_links.sql"),
            [
                (
                    "at://post/a",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "Artist A",
                    "direct_mbid",
                    100.0,
                    "mbid",
                    post_time,
                ),
                (
                    "at://post/b",
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                    "Artist B",
                    "direct_mbid",
                    100.0,
                    "mbid",
                    post_time,
                ),
            ],
        )
        connection.executemany(
            load_sql("upsert_stg_tag_genre_map.sql"),
            [
                (
                    "lastfm",
                    "shoegaze",
                    "shoegaze",
                    1.0,
                    "exact",
                    "fixture",
                    post_time,
                ),
                (
                    "lastfm",
                    "ambient",
                    "ambient",
                    1.0,
                    "exact",
                    "fixture",
                    post_time,
                ),
                (
                    "musicbrainz_genre",
                    "ambient",
                    "ambient",
                    1.0,
                    "exact",
                    "fixture",
                    post_time,
                ),
            ],
        )
        connection.execute(
            load_sql("insert_raw_mb_release_groups.sql"),
            (
                "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "Supply Record",
                [
                    {
                        "credit_name": "Artist B",
                        "artist_name": "Artist B",
                        "mbid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "join_phrase": "",
                    }
                ],
                ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
                "2026-07-15",
                ["Album"],
                ["ambient"],
                [],
                post_time,
            ),
        )

    evidence = (await store.load_evidence()).model_copy(
        update={
            "supply_windows": (
                SupplyCollectionWindow(
                    start_date=date(2026, 7, 13),
                    end_date=date(2026, 7, 19),
                    completed_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
                ),
            )
        }
    )
    batch = build_metrics(
        evidence,
        genres,
        computed_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        bootstrap_resamples=200,
        bootstrap_seed=7,
    )
    assert await store.replace(batch) == (3, 1)
    assert await store.replace(batch) == (3, 1)

    by_genre = {row.canonical_genre: row for row in batch.genre_weeks}
    shoegaze = by_genre["shoegaze"]
    assert shoegaze.conversation_score_raw == 7.0
    assert shoegaze.listening_playcount_delta == 50
    assert shoegaze.listening_listeners_delta == 10
    assert shoegaze.listening_score_raw == 100.0
    assert shoegaze.conversation_post_uris == ("at://post/a",)
    assert shoegaze.listening_artist_keys == (
        "mbid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    assert shoegaze.opportunity is not None
    assert shoegaze.opportunity_ci_low is not None
    assert shoegaze.opportunity_ci_high is not None
    assert (
        shoegaze.opportunity_ci_low
        <= shoegaze.opportunity
        <= shoegaze.opportunity_ci_high
    )
    assert sum(row.conversation_index for row in batch.genre_weeks) == pytest.approx(
        0.0
    )
    assert sum(row.supply_index for row in batch.genre_weeks) == pytest.approx(0.0)
    assert sum(
        row.listening_index or 0.0 for row in batch.genre_weeks
    ) == pytest.approx(0.0)
    ecosystem = batch.ecosystem_weeks[0]
    assert ecosystem.shannon_listening_entropy is not None
    assert ecosystem.effective_genres is not None
    assert ecosystem.conversation_hhi is not None
    assert ecosystem.listening_top10_share == pytest.approx(1.0)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        summary = connection.execute(
            load_sql("summarize_mart_metrics.sql")
        ).fetchone()
        bluesky_feed = connection.execute(
            """
            SELECT uri
            FROM mart_.bluesky_music_feed
            ORDER BY uri
            """
        ).fetchall()
    assert summary == (3, 1)
    assert bluesky_feed == [("at://post/a",), ("at://post/b",)]


@pytest.mark.asyncio
async def test_same_week_lastfm_repoll_is_not_a_weekly_delta(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "same-week.duckdb"
    store = DuckDBMetricStore(database_path)
    await store.initialize()
    first_poll = datetime(2026, 7, 23, 12, tzinfo=UTC)
    second_poll = datetime(2026, 7, 23, 13, tzinfo=UTC)

    with duckdb.connect(str(database_path)) as connection:
        connection.executemany(
            load_sql("insert_raw_lastfm_artist_snapshots.sql"),
            [
                (
                    "Artist A",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    100,
                    1_000,
                    ["shoegaze"],
                    ["shoegaze"],
                    first_poll,
                ),
                (
                    "Artist A",
                    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    101,
                    1_010,
                    ["shoegaze"],
                    ["shoegaze"],
                    second_poll,
                ),
            ],
        )
        connection.execute(
            load_sql("upsert_stg_tag_genre_map.sql"),
            (
                "lastfm",
                "shoegaze",
                "shoegaze",
                1.0,
                "exact",
                "fixture",
                second_poll,
            ),
        )

    evidence = await store.load_evidence()
    assert len(evidence.listening_candidates) == 1
    candidate = evidence.listening_candidates[0]
    assert candidate.playcount == 1_010
    assert candidate.previous_playcount is None
    assert build_metrics(
        evidence,
        ("shoegaze", "other"),
        computed_at=second_poll,
        bootstrap_resamples=20,
    ).genre_weeks == ()
