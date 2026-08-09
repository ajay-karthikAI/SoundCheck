"""Fixture-DuckDB contracts for the non-breaking API v2 surface."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import duckdb
import pytest
from fastapi.testclient import TestClient

from soundcheck.api.app import create_app
from soundcheck.api.config import ApiSettings
from soundcheck.forecast.storage import DuckDBForecastStore
from soundcheck.forecast.v2_storage import DuckDBForecastV2Store
from soundcheck.metrics.coverage import (
    CoverageBatch,
    EligibilityState,
    GenreCoverageRow,
)
from soundcheck.metrics.coverage_storage import (
    initialize_coverage_storage,
    replace_coverage_batch,
)
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.metrics.v2_models import (
    ConversationReceiptV2,
    EcosystemWeekV2,
    GenreWeekV2,
    ListeningReceiptV2,
    MetricEstimateV2,
    MetricName,
    MetricsV2Batch,
    SupplyReceiptV2,
)
from soundcheck.metrics.v2_storage import DuckDBMetricV2Store
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import GenreTaxonomy, load_taxonomy

TAXONOMY_PATH = Path("tests/fixtures/taxonomy_v2.yml")
WEEK = date(2026, 7, 20)
PREVIOUS_WEEK = WEEK - timedelta(weeks=1)
TARGET_WEEK = WEEK + timedelta(weeks=1)
NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
V1_OPENAPI_BASELINE = Path("tests/fixtures/openapi_v1_paths.json")
V2_PATHS = {
    "/api/v2/taxonomy",
    "/api/v2/macro-families",
    "/api/v2/genres/search",
    "/api/v2/opportunities",
    "/api/v2/genres/{genre_id}/timeseries",
    "/api/v2/genres/{genre_id}/evidence",
    "/api/v2/forecasts",
    "/api/v2/forecast/next-up",
    "/api/v2/ecosystem",
    "/api/v2/briefs",
    "/api/v2/scene-map",
    "/api/v2/coverage",
}


@pytest.fixture
def api_v2_client(tmp_path: Path) -> Iterator[TestClient]:
    database_path = tmp_path / "api-v2.duckdb"
    _build_database(database_path)
    app = create_app(
        ApiSettings(
            database_path=database_path,
            taxonomy_path=TAXONOMY_PATH,
        )
    )
    with TestClient(app) as client:
        yield client


def test_v1_openapi_paths_and_health_remain_unchanged(
    api_v2_client: TestClient,
) -> None:
    schema = api_v2_client.get("/openapi.json").json()
    baseline = json.loads(V1_OPENAPI_BASELINE.read_text(encoding="utf-8"))
    actual_v1 = {
        path: sorted(schema["paths"][path])
        for path in schema["paths"]
        if not path.startswith("/api/v2")
    }

    assert actual_v1 == baseline
    assert set(schema["paths"]) >= V2_PATHS
    health = api_v2_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["datastore_mode"] == "read_only"


def test_taxonomy_search_filters_and_cursor_pagination(
    api_v2_client: TestClient,
) -> None:
    first = api_v2_client.get(
        "/api/v2/taxonomy",
        params={"limit": 2},
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["taxonomy_version"] == "2.0.0"
    assert len(payload["genres"]["items"]) == 2
    assert payload["genres"]["page"]["has_more"] is True
    cursor = payload["genres"]["page"]["next_cursor"]

    second = api_v2_client.get(
        "/api/v2/taxonomy",
        params={"limit": 2, "cursor": cursor},
    ).json()
    assert second["genres"]["items"]
    assert {
        row["genre_id"] for row in payload["genres"]["items"]
    }.isdisjoint({row["genre_id"] for row in second["genres"]["items"]})

    search = api_v2_client.get(
        "/api/v2/genres/search",
        params={"q": "garage", "macro_family_id": "macro_rock"},
    )
    assert search.status_code == 200
    assert [row["genre_id"] for row in search.json()["items"]] == [
        "genre_garage_rock"
    ]
    assert search.json()["items"][0]["coverage_status"] == "ready"

    invalid_cursor = api_v2_client.get(
        "/api/v2/taxonomy",
        params={"cursor": "not-a-cursor"},
    )
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["detail"]["code"] == "invalid_cursor"


def test_opportunity_context_filters_uncertainty_and_missingness(
    api_v2_client: TestClient,
) -> None:
    ready = api_v2_client.get(
        "/api/v2/opportunities",
        params={
            "week": WEEK.isoformat(),
            "macro_family_id": "macro_rock",
            "context": "peer_family",
        },
    )
    assert ready.status_code == 200
    items = ready.json()["items"]
    assert {row["genre"]["genre_id"] for row in items} == {
        "genre_garage_rock",
        "genre_rock",
    }
    assert all(row["context"] == "peer_family" for row in items)
    assert all(
        row["opportunity"]["lower"]
        <= row["opportunity"]["value"]
        <= row["opportunity"]["upper"]
        for row in items
    )

    first_page = api_v2_client.get(
        "/api/v2/opportunities",
        params={
            "week": WEEK.isoformat(),
            "macro_family_id": "macro_rock",
            "context": "global",
            "limit": 1,
        },
    ).json()
    second_page = api_v2_client.get(
        "/api/v2/opportunities",
        params={
            "week": WEEK.isoformat(),
            "macro_family_id": "macro_rock",
            "context": "global",
            "limit": 1,
            "cursor": first_page["page"]["next_cursor"],
        },
    ).json()
    assert first_page["page"]["has_more"] is True
    assert (
        first_page["items"][0]["genre"]["genre_id"]
        != second_page["items"][0]["genre"]["genre_id"]
    )

    cold = api_v2_client.get(
        "/api/v2/opportunities",
        params={
            "week": WEEK.isoformat(),
            "eligibility_state": "collecting_history",
        },
    )
    cold_item = cold.json()["items"][0]
    assert cold_item["genre"]["genre_id"] == "genre_uk_garage"
    assert cold_item["opportunity"] is None
    assert cold_item["listening"] is None


def test_timeseries_forecasts_skill_and_cold_start(
    api_v2_client: TestClient,
) -> None:
    timeseries = api_v2_client.get(
        "/api/v2/genres/genre_garage_rock/timeseries",
        params={"context": "global", "weeks": 2},
    )
    assert timeseries.status_code == 200
    payload = timeseries.json()
    assert payload["genre"]["slug"] == "garage-rock"
    assert len(payload["history"]) == 2
    assert payload["history"][-1]["opportunity"] is not None
    publishable = payload["forecasts"]
    assert publishable
    assert all(row["prediction_interval_80"] is not None for row in publishable)
    assert all(row["genre_validation"]["coverage_80"] is not None for row in publishable)
    assert all(row["naive_baseline"] is not None for row in publishable)

    cold = api_v2_client.get(
        "/api/v2/forecasts",
        params={
            "context": "global",
            "macro_family_id": "macro_electronic",
        },
    )
    cold_rows = cold.json()["items"]
    assert cold_rows
    assert all(row["forecast_status"] == "insufficient_history" for row in cold_rows)
    assert all(row["model"] is None for row in cold_rows)
    assert all(row["genre_validation"] is None for row in cold_rows)


@pytest.mark.parametrize(
    ("source", "receipt_key"),
    [
        ("conversation", "post_uri"),
        ("listening", "playcount_delta"),
        ("supply", "release_group_mbid"),
    ],
)
def test_evidence_keeps_direct_source_receipts(
    api_v2_client: TestClient,
    source: str,
    receipt_key: str,
) -> None:
    response = api_v2_client.get(
        "/api/v2/genres/genre_garage_rock/evidence",
        params={"source": source, "week": WEEK.isoformat()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["genre"]["genre_id"] == "genre_garage_rock"
    assert payload["source"] == source
    assert payload["items"][0]["source"] == source
    assert receipt_key in payload["items"][0]


def test_next_up_ecosystem_briefs_scene_and_coverage(
    api_v2_client: TestClient,
) -> None:
    next_up = api_v2_client.get("/api/v2/forecast/next-up").json()
    assert next_up["items"][0]["genre"]["genre_id"] == "genre_garage_rock"
    assert next_up["items"][0]["conversation"]["mase"] == 0.7
    assert next_up["items"][0]["predicted_gain"]["lower"] <= 0.2

    ecosystem = api_v2_client.get(
        "/api/v2/ecosystem",
        params={"context": "peer_family", "macro_family_id": "macro_rock"},
    ).json()
    assert ecosystem[0]["macro_family_id"] == "macro_rock"
    assert ecosystem[0]["listening_entropy"]["lower"] <= 0.6

    briefs = api_v2_client.get("/api/v2/briefs").json()
    assert briefs["items"][0]["brief_id"] == "brief-garage-rock"
    assert briefs["items"][0]["backtest_coverage_80"] == 0.8

    scene = api_v2_client.get("/api/v2/scene-map").json()
    assert scene["items"][0]["genre"]["genre_id"] == "genre_garage_rock"
    assert scene["items"][0]["opportunity"]["value"] == 1.1

    coverage = api_v2_client.get(
        "/api/v2/coverage",
        params={"parent_genre_id": "genre_rock"},
    ).json()
    assert [row["genre"]["genre_id"] for row in coverage["items"]] == [
        "genre_garage_rock"
    ]
    assert coverage["items"][0]["missing_axes"] == []

    missing = api_v2_client.get(
        "/api/v2/coverage",
        params={"eligibility_state": "collecting_history"},
    ).json()["items"][0]
    assert missing["artists_with_consecutive_valid_snapshots"] is None
    assert missing["missing_axes"] == ["listening"]


def test_typed_identifier_version_and_week_errors(
    api_v2_client: TestClient,
) -> None:
    unknown = api_v2_client.get(
        "/api/v2/genres/genre_does_not_exist/timeseries"
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "unknown_genre_id"

    bad_family = api_v2_client.get(
        "/api/v2/opportunities",
        params={"macro_family_id": "macro_missing"},
    )
    assert bad_family.status_code == 404
    assert bad_family.json()["detail"]["code"] == "unknown_macro_family_id"

    bad_version = api_v2_client.get(
        "/api/v2/coverage",
        params={"taxonomy_version": "2.9.0"},
    )
    assert bad_version.status_code == 422
    assert bad_version.json()["detail"]["code"] == "invalid_taxonomy_version"

    future = api_v2_client.get(
        "/api/v2/opportunities",
        params={"week": "2030-01-07"},
    )
    assert future.status_code == 422
    assert future.json()["detail"]["code"] == "future_week"


def _build_database(database_path: Path) -> None:
    asyncio.run(DuckDBMetricStore(database_path).initialize())
    asyncio.run(DuckDBForecastStore(database_path).initialize())
    initialize_coverage_storage(database_path)
    taxonomy = load_taxonomy(TAXONOMY_PATH)
    coverage = _coverage_rows(taxonomy)
    replace_coverage_batch(
        database_path,
        CoverageBatch(
            taxonomy_version=taxonomy.taxonomy_version,
            start_week=WEEK,
            end_week=WEEK,
            computed_at=NOW,
            rows=coverage,
        ),
    )
    v2_store = DuckDBMetricV2Store(database_path)
    asyncio.run(v2_store.initialize())
    asyncio.run(v2_store.replace(_metrics_batch(taxonomy)))
    asyncio.run(DuckDBForecastV2Store(database_path).initialize())
    _insert_forecasts_and_surfaces(database_path)


def _coverage_rows(
    taxonomy: GenreTaxonomy,
) -> tuple[GenreCoverageRow, ...]:
    family_names = {
        family.macro_family_id: family.display_name
        for family in taxonomy.macro_families
    }
    rows: list[GenreCoverageRow] = []
    for genre in taxonomy.genres:
        state: EligibilityState
        if genre.genre_id in {"genre_rock", "genre_garage_rock"}:
            state = "ready"
            artists = 12
            missing = False
        elif genre.genre_id == "genre_uk_garage":
            state = "collecting_history"
            artists = None
            missing = True
        else:
            state = "unsupported"
            artists = None
            missing = True
        ready = state == "ready"
        collecting = state == "collecting_history"
        observed = ready or collecting
        iso = WEEK.isocalendar()
        rows.append(
            GenreCoverageRow(
                taxonomy_version=taxonomy.taxonomy_version,
                week_start=WEEK,
                iso_year=iso.year,
                iso_week=iso.week,
                genre_id=genre.genre_id,
                display_name=genre.display_name,
                slug=genre.slug,
                macro_family_id=genre.macro_family_id,
                macro_family_name=family_names[genre.macro_family_id],
                taxonomy_status=genre.status,
                lastfm_tag_available=True if observed else None,
                unique_lastfm_artists=20 if observed else None,
                artists_with_consecutive_valid_snapshots=artists,
                lastfm_history_weeks=12 if ready else 1 if collecting else None,
                musicbrainz_release_group_count=2 if observed else None,
                resolved_bluesky_post_count=8 if observed else None,
                resolution_attempt_count=10 if observed else None,
                resolution_rate=0.8 if observed else None,
                cross_source_overlap_artist_count=3 if ready else None,
                cross_source_overlap=0.3 if ready else None,
                latest_source_timestamp=NOW if observed else None,
                listening_missing=missing,
                conversation_missing=state == "unsupported",
                supply_missing=state == "unsupported",
                stale=state == "unsupported",
                eligibility_state=state,
                computed_at=NOW,
            )
        )
    return tuple(rows)


def _metrics_batch(taxonomy: GenreTaxonomy) -> MetricsV2Batch:
    genre_rows: list[GenreWeekV2] = []
    estimates: list[MetricEstimateV2] = []
    status_by_genre = {
        row.genre_id: row.eligibility_state for row in _coverage_rows(taxonomy)
    }
    values = {
        "genre_garage_rock": 1.0,
        "genre_rock": 0.4,
    }
    for week_index, week in enumerate((PREVIOUS_WEEK, WEEK)):
        iso = week.isocalendar()
        for genre in taxonomy.genres:
            state = status_by_genre[genre.genre_id]
            ready = state == "ready"
            base = values.get(genre.genre_id, 0.0) + week_index * 0.1
            genre_rows.append(
                GenreWeekV2(
                    taxonomy_version=taxonomy.taxonomy_version,
                    week_start=week,
                    iso_year=iso.year,
                    iso_week=iso.week,
                    genre_id=genre.genre_id,
                    display_name=genre.display_name,
                    macro_family_id=genre.macro_family_id,
                    parent_genre_id=genre.parent_genre_id,
                    coverage_state=state,
                    estimate_status="ready" if ready else state,
                    estimate_eligible=ready,
                    conversation_score_raw=10.0 if ready else None,
                    listening_playcount_delta=100.0 if ready else None,
                    listening_listeners_delta=10.0 if ready else None,
                    listening_score_raw=150.0 if ready else None,
                    supply_release_groups_raw=2.0 if ready else None,
                    conversation_score_shrunk=8.0 if ready else None,
                    conversation_effective_n=10.0 if ready else None,
                    conversation_subgenre_shrinkage_weight=0.8 if ready else None,
                    conversation_family_shrinkage_weight=0.9 if ready else None,
                    conversation_combined_shrinkage_weight=0.72 if ready else None,
                    listening_effective_n=12.0 if ready else None,
                    listening_shrinkage_weight=0.0 if ready else None,
                    supply_rate_shrunk=1.5 if ready else None,
                    supply_family_prior_mean=1.0 if ready else None,
                    supply_global_prior_mean=1.0 if ready else None,
                    supply_effective_n=2.0 if ready else None,
                    supply_subgenre_shrinkage_weight=0.6 if ready else None,
                    supply_family_shrinkage_weight=0.8 if ready else None,
                    supply_combined_shrinkage_weight=0.48 if ready else None,
                    breakout_global=ready and genre.genre_id == "genre_garage_rock",
                    breakout_peer_family=ready
                    and genre.genre_id == "genre_garage_rock",
                    conversation_post_uris=("at://post/garage",) if ready else (),
                    listening_artist_keys=("mbid:garage",) if ready else (),
                    supply_release_group_mbids=("release-garage",) if ready else (),
                    computed_at=NOW,
                )
            )
            for context in ("global", "peer_family"):
                metric_values: tuple[tuple[MetricName, float], ...] = (
                    ("conversation", base),
                    ("listening", base + 0.2),
                    ("supply", base - 0.3),
                    ("opportunity", base),
                    ("discovery_gap", 0.2),
                )
                for metric_name, estimate in metric_values:
                    point = estimate if ready else None
                    estimates.append(
                        MetricEstimateV2(
                            taxonomy_version=taxonomy.taxonomy_version,
                            week_start=week,
                            scope_type="genre",
                            scope_id=genre.genre_id,
                            macro_family_id=genre.macro_family_id,
                            context=context,
                            metric_name=metric_name,
                            estimate_status="ready" if ready else state,
                            estimate=point,
                            ci_low=None if point is None else point - 0.2,
                            ci_high=None if point is None else point + 0.2,
                            ewma=None if point is None else point - 0.05,
                            ewma_ci_low=None if point is None else point - 0.25,
                            ewma_ci_high=None if point is None else point + 0.15,
                            spike=False if point is not None else None,
                            computed_at=NOW,
                        )
                    )
    ecosystem_scopes: tuple[
        tuple[Literal["global", "macro_family"], str], ...
    ] = (
        ("global", "global"),
        ("macro_family", "macro_rock"),
    )
    ecosystems = tuple(
        _ecosystem(taxonomy.taxonomy_version, week, scope_type, scope_id)
        for week in (PREVIOUS_WEEK, WEEK)
        for scope_type, scope_id in ecosystem_scopes
    )
    return MetricsV2Batch(
        taxonomy_version=taxonomy.taxonomy_version,
        genre_weeks=tuple(genre_rows),
        macro_family_weeks=(),
        estimates=tuple(estimates),
        ecosystem_weeks=ecosystems,
        conversation_evidence=(
            ConversationReceiptV2(
                taxonomy_version=taxonomy.taxonomy_version,
                week_start=WEEK,
                genre_id="genre_garage_rock",
                macro_family_id="macro_rock",
                post_uri="at://post/garage",
                did="did:plc:garage",
                created_at=NOW,
                text="Garage rock is on repeat",
                likes=12,
                reposts=3,
                replies=2,
                artist_name_raw="Garage Artist",
                resolution_method="direct_mbid",
                resolution_score=100.0,
                join_key_type="mbid",
                membership_weight=1.0,
                membership_method="exact_alias",
                membership_confidence=0.99,
            ),
        ),
        listening_evidence=(
            ListeningReceiptV2(
                taxonomy_version=taxonomy.taxonomy_version,
                week_start=WEEK,
                genre_id="genre_garage_rock",
                macro_family_id="macro_rock",
                artist_key="mbid:garage",
                artist_name="Garage Artist",
                artist_mbid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                playcount=1_100,
                listeners=120,
                previous_playcount=1_000,
                previous_listeners=100,
                playcount_delta=100,
                listeners_delta=20,
                fetched_at=NOW,
                previous_fetched_at=NOW - timedelta(weeks=1),
                interval_days=7.0,
                listening_window_status="valid_weekly",
                membership_weight=1.0,
                membership_method="exact_alias",
                membership_confidence=0.99,
            ),
        ),
        supply_evidence=(
            SupplyReceiptV2(
                taxonomy_version=taxonomy.taxonomy_version,
                week_start=WEEK,
                genre_id="genre_garage_rock",
                macro_family_id="macro_rock",
                release_group_mbid="release-garage",
                title="Garage Record",
                artist_credits=(
                    {
                        "credit_name": "Garage Artist",
                        "artist_name": "Garage Artist",
                        "mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "join_phrase": "",
                    },
                ),
                first_release_date=WEEK + timedelta(days=2),
                types=("Album",),
                genres=("garage rock",),
                fetched_at=NOW,
                membership_weight=1.0,
            ),
        ),
    )


def _ecosystem(
    version: str,
    week: date,
    scope_type: Literal["global", "macro_family"],
    scope_id: str,
) -> EcosystemWeekV2:
    iso = week.isocalendar()
    return EcosystemWeekV2(
        taxonomy_version=version,
        week_start=week,
        iso_year=iso.year,
        iso_week=iso.week,
        scope_type=scope_type,
        scope_id=scope_id,
        estimate_status="ready",
        listening_entropy=0.6,
        listening_entropy_ci_low=0.5,
        listening_entropy_ci_high=0.7,
        effective_genres=1.8,
        effective_genres_ci_low=1.6,
        effective_genres_ci_high=2.0,
        conversation_hhi=0.3,
        conversation_hhi_ci_low=0.2,
        conversation_hhi_ci_high=0.4,
        listening_top_share=0.7,
        listening_top_share_ci_low=0.6,
        listening_top_share_ci_high=0.8,
        listening_top_share_k=2,
        churn_jaccard_4w=0.5,
        churn_jaccard_4w_ci_low=0.4,
        churn_jaccard_4w_ci_high=0.6,
        breakout_genres=("genre_garage_rock",),
        eligible_genres=2,
        computed_at=NOW,
    )


def _insert_forecasts_and_surfaces(database_path: Path) -> None:
    with duckdb.connect(str(database_path)) as connection:
        prediction_rows = [
            _prediction_row("conversation", "ready", "ets", 0.8, 0.7, 12),
            _prediction_row("listening", "no_skill", "naive", 1.0, 1.0, 12),
            _cold_prediction_row("conversation"),
            _cold_prediction_row("listening"),
        ]
        connection.executemany(
            load_sql("insert_fcst_prediction_v2.sql"),
            prediction_rows,
        )
        connection.execute(
            load_sql("refresh_fcst_next_up_v2.sql"),
            ["2.0.0", "2.0.0"],
        )
        connection.execute(
            """
            INSERT INTO mart_.briefs_v2 VALUES (
                '2.0.0', 'brief-garage-rock', ?, 'genre_garage_rock',
                'Garage Rock', 'macro_rock', 'genre_rock', 'ready', 'global',
                'Garage rock has room to move', 1.0, 0.8, 1.2,
                0.2, -0.2, 0.6, 'ets', 0.7, 0.8,
                'Listening change is rising ahead of release supply.',
                ['Keep the arrangement raw.'], ['at://post/garage'], ?
            )
            """,
            [WEEK, NOW],
        )
        connection.execute(
            """
            INSERT INTO mart_.scene_map_v2 VALUES (
                '2.0.0', ?, 'genre_garage_rock', 'Garage Rock',
                'macro_rock', 'genre_rock', 'ready', 'global',
                1.0, 2.0, 1.0, 0.8, 1.2, 0.2, 0.0, 0.4, 3, ?
            )
            """,
            [WEEK, NOW],
        )


def _prediction_row(
    axis: str,
    status: str,
    model: str,
    point: float,
    mase: float,
    training_weeks: int,
) -> tuple[object, ...]:
    return (
        "2.0.0",
        WEEK,
        TARGET_WEEK,
        "genre_garage_rock",
        "Garage Rock",
        "macro_rock",
        "middle",
        "global",
        axis,
        1,
        status,
        model,
        point,
        point - 0.3,
        point + 0.3,
        mase,
        0.8,
        "scored",
        mase + 0.1,
        0.75,
        "scored",
        point - 0.1,
        point - 0.4,
        point + 0.2,
        1.0,
        0.75,
        "scored",
        training_weeks,
        date(2026, 4, 27),
        WEEK,
        NOW,
    )


def _cold_prediction_row(axis: str) -> tuple[object, ...]:
    return (
        "2.0.0",
        WEEK,
        TARGET_WEEK,
        "genre_uk_garage",
        "UK Garage",
        "macro_electronic",
        "unknown",
        "global",
        axis,
        1,
        "insufficient_history",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        3,
        None,
        None,
        NOW,
    )
