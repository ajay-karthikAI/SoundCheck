"""Last.fm interval integrity and corrected-artifact isolation tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from soundcheck.metrics.listening_windows import classify_listening_window
from soundcheck.metrics.models import (
    ConversationEvidence,
    ListeningDeltaCandidate,
    MetricEvidence,
    SupplyEvidence,
)
from soundcheck.metrics.pipeline import build_metrics
from soundcheck.metrics.storage import DuckDBMetricStore


@pytest.mark.parametrize(
    (
        "previous_at",
        "fetched_at",
        "previous_playcount",
        "playcount",
        "previous_listeners",
        "listeners",
        "expected",
    ),
    (
        (
            None,
            datetime(2026, 7, 23, 12, tzinfo=UTC),
            None,
            1_000,
            None,
            100,
            "first_observation",
        ),
        (
            datetime(2026, 7, 23, 10, tzinfo=UTC),
            datetime(2026, 7, 23, 12, tzinfo=UTC),
            1_000,
            1_010,
            100,
            101,
            "same_week_duplicate",
        ),
        (
            datetime(2026, 7, 19, 23, tzinfo=UTC),
            datetime(2026, 7, 20, 1, tzinfo=UTC),
            1_000,
            1_010,
            100,
            101,
            "valid_weekly",
        ),
        (
            datetime(2026, 7, 23, 12, tzinfo=UTC),
            datetime(2026, 8, 3, 12, tzinfo=UTC),
            1_000,
            1_100,
            100,
            110,
            "nonconsecutive_weeks",
        ),
        (
            datetime(2026, 7, 9, 12, tzinfo=UTC),
            datetime(2026, 7, 23, 12, tzinfo=UTC),
            1_000,
            1_100,
            100,
            110,
            "nonconsecutive_weeks",
        ),
        (
            datetime(2026, 7, 16, 12, tzinfo=UTC),
            datetime(2026, 7, 23, 12, tzinfo=UTC),
            1_000,
            999,
            100,
            110,
            "counter_decrease",
        ),
    ),
)
def test_listening_window_statuses(
    previous_at: datetime | None,
    fetched_at: datetime,
    previous_playcount: int | None,
    playcount: int,
    previous_listeners: int | None,
    listeners: int,
    expected: str,
) -> None:
    assert classify_listening_window(
        previous_fetched_at=previous_at,
        fetched_at=fetched_at,
        previous_playcount=previous_playcount,
        playcount=playcount,
        previous_listeners=previous_listeners,
        listeners=listeners,
    ) == expected


def test_eleven_day_delta_is_not_rescaled_or_used() -> None:
    week = date(2026, 8, 3)
    candidate = ListeningDeltaCandidate(
        week_start=week,
        canonical_genre="shoegaze",
        artist_key="name:artist-a",
        artist_name="Artist A",
        playcount=1_110,
        listeners=111,
        previous_playcount=1_000,
        previous_listeners=100,
        previous_fetched_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
        fetched_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
    )
    assert candidate.interval_days == 11.0
    assert candidate.listening_window_status == "nonconsecutive_weeks"

    batch = build_metrics(
        MetricEvidence(
            conversation=(
                ConversationEvidence(
                    week_start=week,
                    canonical_genre="shoegaze",
                    post_uri="at://post/a",
                    mentions=1,
                    likes=0,
                    reposts=0,
                    replies=0,
                ),
            ),
            listening_candidates=(candidate,),
            supply=(
                SupplyEvidence(
                    week_start=week,
                    canonical_genre="shoegaze",
                    release_group_mbid="release-a",
                ),
            ),
        ),
        ("shoegaze", "other"),
        computed_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
        bootstrap_resamples=10,
    )
    shoegaze = next(
        row for row in batch.genre_weeks if row.canonical_genre == "shoegaze"
    )
    assert shoegaze.listening_score_raw is None
    assert shoegaze.opportunity is None
    assert shoegaze.discovery_gap is None


@pytest.mark.asyncio
async def test_corrected_versions_do_not_rewrite_legacy_or_each_other(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "versions.duckdb"
    store = DuckDBMetricStore(database_path)
    await store.initialize()
    week = date(2026, 7, 20)
    evidence = MetricEvidence(
        conversation=(
            ConversationEvidence(
                week_start=week,
                canonical_genre="shoegaze",
                post_uri="at://post/a",
                mentions=1,
                likes=0,
                reposts=0,
                replies=0,
            ),
        ),
        listening_candidates=(
            ListeningDeltaCandidate(
                week_start=week,
                canonical_genre="shoegaze",
                artist_key="name:artist-a",
                artist_name="Artist A",
                playcount=1_100,
                listeners=110,
                previous_playcount=1_000,
                previous_listeners=100,
                previous_fetched_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
                fetched_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
            ),
        ),
        supply=(
            SupplyEvidence(
                week_start=week,
                canonical_genre="shoegaze",
                release_group_mbid="release-a",
            ),
        ),
    )
    batch = build_metrics(
        evidence,
        ("shoegaze", "other"),
        computed_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        bootstrap_resamples=10,
    )
    await store.replace(batch)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        legacy_before = connection.execute(
            "SELECT * FROM mart_.genre_weekly ORDER BY week_start, canonical_genre"
        ).fetchall()

    await store.replace_corrected(batch, evidence, "lastfm_weekly_v2")
    await store.replace_corrected(batch, evidence, "lastfm_weekly_v3")

    with duckdb.connect(str(database_path), read_only=True) as connection:
        legacy_after = connection.execute(
            "SELECT * FROM mart_.genre_weekly ORDER BY week_start, canonical_genre"
        ).fetchall()
        versions = connection.execute(
            """
            SELECT derivation_version, is_active
            FROM mart_.metric_artifact_versions
            WHERE artifact_family = 'v1'
            ORDER BY derivation_version
            """
        ).fetchall()
        corrected_counts = connection.execute(
            """
            SELECT derivation_version, count(*)
            FROM mart_.genre_weekly_versioned
            GROUP BY derivation_version
            ORDER BY derivation_version
            """
        ).fetchall()
    assert legacy_after == legacy_before
    assert versions == [
        ("lastfm_weekly_v2", False),
        ("lastfm_weekly_v3", True),
    ]
    assert corrected_counts == [
        ("lastfm_weekly_v2", 2),
        ("lastfm_weekly_v3", 2),
    ]
