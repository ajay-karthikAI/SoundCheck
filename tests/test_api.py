"""Fixture-DuckDB contract and edge-case tests for the read-only API."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient

from soundcheck.api.app import create_app
from soundcheck.api.config import ApiSettings
from soundcheck.metrics.models import (
    EcosystemWeekMetric,
    GenreWeekMetric,
    MetricsBatch,
    SceneMapPoint,
)
from soundcheck.metrics.pipeline import build_metrics
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.sql.loader import load_sql

CURRENT_WEEK = date(2026, 7, 13)
COMPUTED_AT = datetime(2026, 7, 20, 12, tzinfo=UTC)


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    database_path = tmp_path / "api-fixture.duckdb"
    _build_fixture_database(database_path)
    api = create_app(
        ApiSettings(
            database_path=database_path,
            production_origin="https://soundcheck.example",
        )
    )
    with TestClient(api) as client:
        yield client


def test_health_openapi_cache_and_cors(api_client: TestClient) -> None:
    health = api_client.get(
        "/api/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert health.status_code == 200
    assert health.headers["cache-control"] == "public, max-age=60"
    assert health.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert health.json() == {
        "status": "ok",
        "datastore_mode": "read_only",
        "latest_metric_week": "2026-07-13",
        "latest_forecast_week": "2026-07-20",
        "latest_complete_week": "2026-07-13",
        "metric_rows": 9,
        "forecast_rows": 4,
        "last_pipeline_run": {
            "run_id": "fixture-weekly",
            "run_kind": "weekly",
            "trigger": "test",
            "git_sha": "abc123",
            "status": "success",
            "started_at": "2026-07-20T11:55:00Z",
            "completed_at": "2026-07-20T12:00:00Z",
            "wall_time_seconds": 300.0,
            "rows_ingested": {
                "bluesky_posts": 2,
                "bluesky_engagement_snapshots": 5,
                "lastfm_tag_snapshots": 3,
                "lastfm_artist_snapshots": 4,
                "musicbrainz_release_groups": 1,
            },
            "resolution_posts_attempted": 2,
            "resolution_links_resolved": 2,
            "resolution_rate": 1.0,
            "metric_rows": 9,
            "forecast_rows": 4,
            "brief_rows": 1,
            "error_message": None,
        },
        "cache_ttl_seconds": 60,
    }

    production_cors = api_client.get(
        "/api/health",
        headers={"Origin": "https://soundcheck.example"},
    )
    assert (
        production_cors.headers["access-control-allow-origin"]
        == "https://soundcheck.example"
    )
    openapi = api_client.get("/openapi.json").json()
    expected_paths = {
        "/api/health",
        "/api/evidence/bluesky",
        "/api/genres/opportunities",
        "/api/genres/{genre}/timeseries",
        "/api/genres/{genre}/evidence",
        "/api/forecast/next-up",
        "/api/ecosystem",
        "/api/briefs",
        "/api/scene-map",
    }
    assert expected_paths <= set(openapi["paths"])


def test_bluesky_feed_publishes_music_context_only(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/api/evidence/bluesky",
        params={"week": CURRENT_WEEK.isoformat(), "limit": 20},
    )
    assert response.status_code == 200
    payload = response.json()
    assert [post["uri"] for post in payload] == [
        "at://post/a",
        "at://post/b",
    ]
    assert payload[0]["matched_rules"] == ["intent:listening_to"]
    assert payload[0]["likes"] == 4
    assert all("history documentary" not in post["text"] for post in payload)


def test_opportunities_default_empty_and_future_week(api_client: TestClient) -> None:
    response = api_client.get("/api/genres/opportunities")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["week"] == "2026-07-13"
    assert {"value", "lower", "upper"} == set(payload[0]["opportunity"])
    assert set(payload[0]["shrinkage_weight"]) == {"conversation", "supply"}
    assert set(payload[0]["spike_flag"]) == {
        "conversation",
        "listening",
        "supply",
    }

    empty = api_client.get(
        "/api/genres/opportunities",
        params={"week": "2026-06-01"},
    )
    assert empty.status_code == 200
    assert empty.json() == []

    future = api_client.get(
        "/api/genres/opportunities",
        params={"week": "2030-01-07"},
    )
    assert future.status_code == 422
    assert future.json()["detail"]["code"] == "future_week"

    not_monday = api_client.get(
        "/api/genres/opportunities",
        params={"week": "2026-07-14"},
    )
    assert not_monday.status_code == 422
    assert not_monday.json()["detail"]["code"] == "invalid_iso_week"


def test_timeseries_forecasts_and_unknown_genre(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/genres/shoegaze/timeseries",
        params={"weeks": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["genre"] == "shoegaze"
    assert [row["week"] for row in payload["history"]] == [
        "2026-07-06",
        "2026-07-13",
    ]
    assert len(payload["forecasts"]) == 2
    assert {row["target_axis"] for row in payload["forecasts"]} == {
        "conversation",
        "listening",
    }
    assert all(row["skill_status"] == "skill" for row in payload["forecasts"])
    assert all(
        row["prediction_interval_80"]["lower"]
        <= row["prediction_interval_80"]["value"]
        <= row["prediction_interval_80"]["upper"]
        for row in payload["forecasts"]
    )

    missing = api_client.get("/api/genres/not-a-genre/timeseries")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "unknown_genre"


def test_evidence_returns_all_three_source_receipts(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/genres/shoegaze/evidence",
        params={"week": CURRENT_WEEK.isoformat(), "limit": 20},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["bluesky_posts"][0] == {
        "uri": "at://post/a",
        "did": "did:plc:a",
        "created_at": "2026-07-15T09:00:00Z",
        "text": "Listening to Artist A",
        "likes": 4,
        "reposts": 2,
        "replies": 1,
        "artist_name_raw": "Artist A",
        "resolution_method": "direct_mbid",
        "resolution_score": 100.0,
        "join_key_type": "mbid",
    }
    assert payload["lastfm_artists"][0]["playcount_delta"] == 50
    assert payload["lastfm_artists"][0]["listeners_delta"] == 10
    assert payload["musicbrainz_releases"] == []

    ambient = api_client.get(
        "/api/genres/ambient/evidence",
        params={"week": CURRENT_WEEK.isoformat()},
    ).json()
    assert ambient["musicbrainz_releases"][0]["title"] == "Supply Record"
    assert (
        ambient["musicbrainz_releases"][0]["artist_credits"][0]["artist_name"]
        == "Artist B"
    )


def test_next_up_ecosystem_briefs_and_scene_map(api_client: TestClient) -> None:
    next_up = api_client.get("/api/forecast/next-up").json()
    assert len(next_up) == 2
    assert next_up[0]["predicted_opportunity"] == {
        "value": 1.1,
        "lower": 0.6,
        "upper": 1.5,
    }
    assert next_up[0]["conversation_model"] == {
        "name": "ets",
        "mase": 0.7,
    }
    assert next_up[1]["skill_status"] == "no_skill"
    assert next_up[1]["conversation_model"]["mase"] == 1.0

    ecosystem = api_client.get("/api/ecosystem", params={"weeks": 2}).json()
    assert len(ecosystem) == 2
    assert ecosystem[-1]["week"] == "2026-07-13"
    assert {"value", "lower", "upper"} == set(
        ecosystem[-1]["listening_entropy"]
    )

    briefs = api_client.get("/api/briefs").json()
    assert len(briefs) == 1
    assert briefs[0]["brief_id"] == "2026-W29-shoegaze"
    assert briefs[0]["opportunity"] == {
        "value": 1.1,
        "lower": 0.6,
        "upper": 1.5,
    }
    assert briefs[0]["evidence_uris"][0].startswith("at://")
    future_briefs = api_client.get(
        "/api/briefs",
        params={"week": "2030-01-07"},
    )
    assert future_briefs.status_code == 422
    assert future_briefs.json()["detail"]["code"] == "future_week"

    scene_map = api_client.get("/api/scene-map").json()
    assert len(scene_map) == 3
    assert all(point["as_of_week"] == "2026-07-13" for point in scene_map)
    assert all("evidence_volume" in point for point in scene_map)


def _build_fixture_database(database_path: Path) -> None:
    store = DuckDBMetricStore(database_path)
    asyncio.run(store.initialize())
    _insert_source_fixtures(database_path)
    evidence = asyncio.run(store.load_evidence())
    latest = build_metrics(
        evidence,
        ("shoegaze", "ambient", "other"),
        computed_at=COMPUTED_AT,
        bootstrap_resamples=100,
        bootstrap_seed=17,
    )
    genre_rows: list[GenreWeekMetric] = []
    ecosystem_rows: list[EcosystemWeekMetric] = []
    for weeks_back in (2, 1):
        shifted_week = CURRENT_WEEK - timedelta(weeks=weeks_back)
        iso = shifted_week.isocalendar()
        genre_rows.extend(
            row.model_copy(
                update={
                    "week_start": shifted_week,
                    "iso_year": iso.year,
                    "iso_week": iso.week,
                    "conversation_post_uris": (),
                    "listening_artist_keys": (),
                    "supply_release_group_mbids": (),
                }
            )
            for row in latest.genre_weeks
        )
        ecosystem_rows.extend(
            row.model_copy(
                update={
                    "week_start": shifted_week,
                    "iso_year": iso.year,
                    "iso_week": iso.week,
                }
            )
            for row in latest.ecosystem_weeks
        )
    genre_rows.extend(latest.genre_weeks)
    ecosystem_rows.extend(latest.ecosystem_weeks)
    latest_by_genre = {
        row.canonical_genre: row for row in latest.genre_weeks
    }
    scene_points = tuple(
        SceneMapPoint(
            as_of_week=CURRENT_WEEK,
            canonical_genre=genre,
            x=float(index),
            y=float(index) / 2.0,
            opportunity=metric.opportunity,
            opportunity_ci_low=metric.opportunity_ci_low,
            opportunity_ci_high=metric.opportunity_ci_high,
            discovery_gap=metric.discovery_gap,
            discovery_gap_ci_low=metric.discovery_gap_ci_low,
            discovery_gap_ci_high=metric.discovery_gap_ci_high,
            evidence_volume=(
                len(metric.conversation_post_uris)
                + len(metric.listening_artist_keys)
                + len(metric.supply_release_group_mbids)
            ),
            computed_at=COMPUTED_AT,
        )
        for index, (genre, metric) in enumerate(
            sorted(latest_by_genre.items())
        )
    )
    asyncio.run(
        store.replace(
            MetricsBatch(
                genre_weeks=tuple(genre_rows),
                ecosystem_weeks=tuple(ecosystem_rows),
                scene_map_points=scene_points,
            )
        )
    )
    _insert_forecast_fixtures(database_path)
    _insert_phase8_fixtures(database_path)


def _insert_source_fixtures(database_path: Path) -> None:
    first_snapshot = datetime(2026, 7, 6, 12, tzinfo=UTC)
    second_snapshot = datetime(2026, 7, 13, 12, tzinfo=UTC)
    post_time = datetime(2026, 7, 15, 9, tzinfo=UTC)
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
                ("at://post/a", 4, 2, 1, post_time),
                ("at://post/b", 0, 0, 0, post_time),
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


def _insert_forecast_fixtures(database_path: Path) -> None:
    target_week = CURRENT_WEEK + timedelta(weeks=1)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_fcst_tables.sql"))
        predictions: list[tuple[Any, ...]] = []
        for axis, skilled_model, point in (
            ("conversation", "ets", 0.8),
            ("listening", "lightgbm", 1.2),
        ):
            predictions.extend(
                [
                    (
                        CURRENT_WEEK,
                        target_week,
                        "shoegaze",
                        axis,
                        1,
                        "naive",
                        True,
                        "baseline",
                        point - 0.1,
                        point - 0.5,
                        point + 0.4,
                        1.0,
                        0.8,
                        12,
                        date(2026, 4, 20),
                        CURRENT_WEEK,
                        COMPUTED_AT,
                    ),
                    (
                        CURRENT_WEEK,
                        target_week,
                        "shoegaze",
                        axis,
                        1,
                        skilled_model,
                        False,
                        "skill",
                        point,
                        point - 0.4,
                        point + 0.3,
                        0.7 if axis == "conversation" else 0.6,
                        0.8,
                        12,
                        date(2026, 4, 20),
                        CURRENT_WEEK,
                        COMPUTED_AT,
                    ),
                ]
            )
        connection.executemany(
            load_sql("insert_fcst_predictions.sql"),
            predictions,
        )
        connection.executemany(
            load_sql("insert_fcst_next_up.sql"),
            [
                (
                    CURRENT_WEEK,
                    target_week,
                    "shoegaze",
                    1,
                    1.1,
                    0.6,
                    1.5,
                    0.4,
                    -0.1,
                    0.8,
                    "ets",
                    "lightgbm",
                    0.7,
                    0.6,
                    "skill",
                    CURRENT_WEEK,
                    COMPUTED_AT,
                ),
                (
                    CURRENT_WEEK,
                    target_week,
                    "ambient",
                    2,
                    0.4,
                    -0.2,
                    1.0,
                    0.1,
                    -0.5,
                    0.7,
                    "naive",
                    "naive",
                    1.0,
                    1.0,
                    "no_skill",
                    CURRENT_WEEK,
                    COMPUTED_AT,
                ),
            ],
        )


def _insert_phase8_fixtures(database_path: Path) -> None:
    started_at = COMPUTED_AT - timedelta(minutes=5)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_mart_briefs.sql"))
        connection.execute(load_sql("create_mart_pipeline_runs.sql"))
        connection.execute(
            load_sql("insert_mart_brief.sql"),
            (
                "2026-W29-shoegaze",
                CURRENT_WEEK,
                "shoegaze",
                "Shoegaze has room to move",
                1.1,
                0.6,
                1.5,
                "Artist A is rising while release supply remains below trend.",
                ["Commission a studio-process feature"],
                ["at://post/a"],
                COMPUTED_AT,
            ),
        )
        connection.execute(
            load_sql("insert_pipeline_run_started.sql"),
            (
                "fixture-weekly",
                "weekly",
                "test",
                "abc123",
                started_at,
            ),
        )
        connection.execute(
            load_sql("update_pipeline_run_finished.sql"),
            (
                "success",
                COMPUTED_AT,
                300.0,
                2,
                5,
                3,
                4,
                1,
                2,
                2,
                1.0,
                9,
                4,
                1,
                None,
                "fixture-weekly",
            ),
        )
