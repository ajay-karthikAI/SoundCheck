"""Fixture-only taxonomy-v2 metric and version-isolation tests."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from soundcheck.metrics.coverage import GenreCoverageRow
from soundcheck.metrics.maturity import SupplyCollectionWindow
from soundcheck.metrics.v2_models import (
    ConversationEvidenceV2,
    ListeningCandidateV2,
    MetricEvidenceV2,
    MetricsV2Batch,
    SupplyEvidenceV2,
)
from soundcheck.metrics.v2_pipeline import build_metrics_v2
from soundcheck.metrics.v2_storage import DuckDBMetricV2Store
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import load_taxonomy

_TAXONOMY_PATH = Path("tests/fixtures/taxonomy_v2.yml")
_COMPUTED_AT = datetime(2026, 7, 27, 12, tzinfo=UTC)
_FIRST_WEEK = date(2026, 7, 13)
_SECOND_WEEK = date(2026, 7, 20)
_NORMAL_GENRES = (
    "genre_rock",
    "genre_garage_rock",
    "genre_uk_garage",
)


def _coverage_row(
    genre_id: str,
    week: date,
    *,
    ready: bool,
) -> GenreCoverageRow:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    genre = taxonomy.genre_by_id[genre_id]
    family = next(
        item
        for item in taxonomy.macro_families
        if item.macro_family_id == genre.macro_family_id
    )
    special = genre_id in {
        taxonomy.other_genre_id,
        taxonomy.unresolved_genre_id,
    }
    iso = week.isocalendar()
    if ready:
        payload = {
            "lastfm_tag_available": True,
            "unique_lastfm_artists": 25,
            "artists_with_consecutive_valid_snapshots": 10,
            "lastfm_history_weeks": 2,
            "musicbrainz_release_group_count": 1,
            "resolved_bluesky_post_count": 5,
            "resolution_attempt_count": 5,
            "resolution_rate": 0.9,
            "cross_source_overlap_artist_count": 2,
            "cross_source_overlap": 0.2,
            "latest_source_timestamp": _COMPUTED_AT,
            "listening_missing": False,
            "conversation_missing": False,
            "supply_missing": False,
            "stale": False,
            "eligibility_state": "ready",
        }
    elif special:
        payload = {
            "lastfm_tag_available": None,
            "unique_lastfm_artists": None,
            "artists_with_consecutive_valid_snapshots": None,
            "lastfm_history_weeks": None,
            "musicbrainz_release_group_count": None,
            "resolved_bluesky_post_count": None,
            "resolution_attempt_count": None,
            "resolution_rate": None,
            "cross_source_overlap_artist_count": None,
            "cross_source_overlap": None,
            "latest_source_timestamp": None,
            "listening_missing": True,
            "conversation_missing": True,
            "supply_missing": True,
            "stale": True,
            "eligibility_state": "unsupported",
        }
    else:
        payload = {
            "lastfm_tag_available": True,
            "unique_lastfm_artists": 25,
            "artists_with_consecutive_valid_snapshots": None,
            "lastfm_history_weeks": 1,
            "musicbrainz_release_group_count": 1,
            "resolved_bluesky_post_count": 5,
            "resolution_attempt_count": 5,
            "resolution_rate": 0.9,
            "cross_source_overlap_artist_count": 2,
            "cross_source_overlap": 0.2,
            "latest_source_timestamp": _COMPUTED_AT,
            "listening_missing": True,
            "conversation_missing": False,
            "supply_missing": False,
            "stale": False,
            "eligibility_state": "collecting_history",
        }
    return GenreCoverageRow.model_validate(
        {
            "taxonomy_version": taxonomy.taxonomy_version,
            "week_start": week,
            "iso_year": iso.year,
            "iso_week": iso.week,
            "genre_id": genre.genre_id,
            "display_name": genre.display_name,
            "slug": genre.slug,
            "macro_family_id": genre.macro_family_id,
            "macro_family_name": family.display_name,
            "taxonomy_status": genre.status,
            **payload,
            "computed_at": _COMPUTED_AT,
        }
    )


def _fixture_evidence() -> MetricEvidenceV2:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    coverage = tuple(
        _coverage_row(
            genre.genre_id,
            week,
            ready=week == _SECOND_WEEK
            and genre.genre_id in _NORMAL_GENRES,
        )
        for week in (_FIRST_WEEK, _SECOND_WEEK)
        for genre in taxonomy.genres
    )
    family_by_genre = {
        genre.genre_id: genre.macro_family_id
        for genre in taxonomy.genres
    }
    conversation = tuple(
        ConversationEvidenceV2(
            week_start=_SECOND_WEEK,
            genre_id=genre_id,
            macro_family_id=family_by_genre[genre_id],
            post_uri=f"at://post/{index}",
            membership_weight=1.0,
            likes=likes,
            reposts=index,
            replies=0,
        )
        for index, (genre_id, likes) in enumerate(
            zip(_NORMAL_GENRES, (10, 2, 0), strict=True),
            start=1,
        )
    )
    first_snapshots = tuple(
        ListeningCandidateV2(
            week_start=_FIRST_WEEK,
            genre_id=genre_id,
            macro_family_id=family_by_genre[genre_id],
            artist_key=f"mbid:{index}",
            membership_weight=1.0,
            playcount=1_000,
            listeners=100,
            fetched_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
        )
        for index, genre_id in enumerate(_NORMAL_GENRES)
    )
    deltas = ((100, 10), (50, 5), (20, 20))
    second_snapshots = tuple(
        ListeningCandidateV2(
            week_start=_SECOND_WEEK,
            genre_id=genre_id,
            macro_family_id=family_by_genre[genre_id],
            artist_key=f"mbid:{index}",
            membership_weight=1.0,
            playcount=1_000 + delta[0],
            listeners=100 + delta[1],
            previous_playcount=1_000,
            previous_listeners=100,
            fetched_at=datetime(2026, 7, 23, 12, tzinfo=UTC),
            previous_fetched_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
        )
        for index, (genre_id, delta) in enumerate(
            zip(_NORMAL_GENRES, deltas, strict=True)
        )
    )
    supply = tuple(
        SupplyEvidenceV2(
            week_start=_SECOND_WEEK,
            genre_id=genre_id,
            macro_family_id=family_by_genre[genre_id],
            release_group_mbid=f"release-{genre_id}-{release_index}",
            membership_weight=1.0,
        )
        for genre_id, count in zip(_NORMAL_GENRES, (2, 1, 3), strict=True)
        for release_index in range(count)
    )
    return MetricEvidenceV2(
        taxonomy_version=taxonomy.taxonomy_version,
        conversation=conversation,
        listening_candidates=(*first_snapshots, *second_snapshots),
        supply=supply,
        coverage=coverage,
        supply_windows=(
            SupplyCollectionWindow(
                start_date=_SECOND_WEEK,
                end_date=date(2026, 7, 26),
                completed_at=_COMPUTED_AT,
            ),
        ),
    )


def test_v2_metrics_preserve_missingness_contexts_and_uncertainty() -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    batch = build_metrics_v2(
        _fixture_evidence(),
        taxonomy,
        computed_at=_COMPUTED_AT,
        bootstrap_resamples=80,
        bootstrap_seed=11,
    )

    assert len(batch.genre_weeks) == 10
    first_week = {
        row.genre_id: row
        for row in batch.genre_weeks
        if row.week_start == _FIRST_WEEK
    }
    assert first_week["genre_rock"].listening_score_raw is None
    assert not first_week["genre_rock"].estimate_eligible

    second_week = {
        row.genre_id: row
        for row in batch.genre_weeks
        if row.week_start == _SECOND_WEEK
    }
    assert second_week["genre_rock"].listening_playcount_delta == 100.0
    assert second_week["genre_rock"].listening_listeners_delta == 10.0
    assert second_week["genre_rock"].listening_score_raw == 150.0
    assert second_week["genre_other"].coverage_state == "unsupported"
    assert second_week["genre_other"].conversation_score_raw is None
    assert not second_week["genre_other"].estimate_eligible

    estimates = tuple(
        row
        for row in batch.estimates
        if row.week_start == _SECOND_WEEK
        and row.scope_type == "genre"
    )
    for context in ("global", "peer_family"):
        for metric in ("conversation", "listening", "supply"):
            values = [
                row.estimate
                for row in estimates
                if row.context == context
                and row.metric_name == metric
                and row.estimate is not None
            ]
            assert sum(values) == pytest.approx(0.0, abs=1e-8)
    peer_rock = [
        row.estimate
        for row in estimates
        if row.context == "peer_family"
        and row.metric_name == "opportunity"
        and row.scope_id in {"genre_rock", "genre_garage_rock"}
    ]
    assert sum(value for value in peer_rock if value is not None) == pytest.approx(
        0.0,
        abs=1e-8,
    )
    ready_estimates = [row for row in estimates if row.estimate is not None]
    assert ready_estimates
    for row in ready_estimates:
        assert row.estimate is not None
        assert row.ci_low is not None
        assert row.ci_high is not None
        assert row.ci_low <= row.estimate <= row.ci_high
    missing_estimates = [
        row for row in estimates if row.scope_id == "genre_other"
    ]
    assert all(
        row.estimate is None and row.ci_low is None and row.ci_high is None
        for row in missing_estimates
    )


@pytest.mark.asyncio
async def test_v2_source_queries_accept_an_empty_fixture_database(
    tmp_path: Path,
) -> None:
    store = DuckDBMetricV2Store(tmp_path / "empty-evidence.duckdb")
    await store.initialize()

    evidence = await store.load_evidence("2.0.0")

    assert evidence.conversation == ()
    assert evidence.listening_candidates == ()
    assert evidence.supply == ()
    assert evidence.coverage == ()


def _with_version(batch: MetricsV2Batch, version: str) -> MetricsV2Batch:
    return MetricsV2Batch(
        taxonomy_version=version,
        genre_weeks=tuple(
            row.model_copy(update={"taxonomy_version": version})
            for row in batch.genre_weeks
        ),
        macro_family_weeks=tuple(
            row.model_copy(update={"taxonomy_version": version})
            for row in batch.macro_family_weeks
        ),
        estimates=tuple(
            row.model_copy(update={"taxonomy_version": version})
            for row in batch.estimates
        ),
        ecosystem_weeks=tuple(
            row.model_copy(update={"taxonomy_version": version})
            for row in batch.ecosystem_weeks
        ),
    )


@pytest.mark.asyncio
async def test_v2_storage_replaces_only_one_taxonomy_version(
    tmp_path: Path,
) -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    original = build_metrics_v2(
        _fixture_evidence(),
        taxonomy,
        computed_at=_COMPUTED_AT,
        bootstrap_resamples=20,
        bootstrap_seed=3,
    )
    other_version = _with_version(original, "2.1.0")
    database_path = tmp_path / "metrics-v2.duckdb"
    store = DuckDBMetricV2Store(database_path)
    await store.initialize()

    await store.replace(original)
    await store.replace(other_version)
    await store.replace(original)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        counts = connection.execute(
            load_sql("summarize_mart_metrics_v2_versions.sql")
        ).fetchall()
    assert counts == [
        ("2.0.0", len(original.genre_weeks)),
        ("2.1.0", len(other_version.genre_weeks)),
    ]


@pytest.mark.asyncio
async def test_corrected_v2_storage_audits_windows_without_rewriting_legacy(
    tmp_path: Path,
) -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    evidence = _fixture_evidence()
    batch = build_metrics_v2(
        evidence,
        taxonomy,
        computed_at=_COMPUTED_AT,
        bootstrap_resamples=20,
        bootstrap_seed=3,
    )
    database_path = tmp_path / "corrected-v2.duckdb"
    store = DuckDBMetricV2Store(database_path)
    await store.initialize()

    await store.replace_corrected(batch, evidence)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        legacy_count = connection.execute(
            "SELECT count(*) FROM mart_.genre_weekly_v2"
        ).fetchone()
        corrected_count = connection.execute(
            "SELECT count(*) FROM mart_.genre_weekly_v2_versioned"
        ).fetchone()
        statuses = connection.execute(
            """
            SELECT listening_window_status, count(*)
            FROM mart_.lastfm_listening_windows
            WHERE artifact_family = 'v2'
            GROUP BY listening_window_status
            ORDER BY listening_window_status
            """
        ).fetchall()
    assert legacy_count == (0,)
    assert corrected_count == (len(batch.genre_weeks),)
    assert statuses == [("first_observation", 3), ("valid_weekly", 3)]
