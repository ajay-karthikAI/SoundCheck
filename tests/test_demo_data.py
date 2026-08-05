"""The isolated demo artifact populates every frozen API surface."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from soundcheck.api.app import create_app
from soundcheck.api.config import ApiSettings
from soundcheck.scripts.seed_demo import (
    DEMO_GENRE_DEFINITIONS,
    DEMO_GENRES,
    DEMO_MACRO_FAMILIES,
    DEMO_TAXONOMY,
    PRODUCTION_DATABASE_PATH,
    DemoSettings,
    seed_demo_database,
)


def test_demo_generator_refuses_production_database() -> None:
    with pytest.raises(ValidationError):
        DemoSettings(output_path=PRODUCTION_DATABASE_PATH)


def test_demo_artifact_populates_every_api_tab(tmp_path: Path) -> None:
    database_path = tmp_path / "soundcheck-demo.duckdb"
    summary = asyncio.run(
        seed_demo_database(
            DemoSettings(
                output_path=database_path,
                as_of_date=datetime.now(UTC).date(),
                weeks=10,
                bootstrap_resamples=25,
            )
        )
    )
    assert summary.data_mode == "synthetic_demo"
    assert summary.taxonomy_version == DEMO_TAXONOMY.taxonomy_version
    assert summary.macro_families == DEMO_MACRO_FAMILIES == 15
    assert summary.genres == len(DEMO_GENRES)
    assert summary.enabled_genres == sum(
        genre.status == "enabled" for genre in DEMO_GENRE_DEFINITIONS
    )
    assert summary.candidate_genres == sum(
        genre.status == "candidate" for genre in DEMO_GENRE_DEFINITIONS
    )
    assert summary.next_up_rows > 0
    assert summary.brief_rows > 0

    app = create_app(ApiSettings(database_path=database_path))
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["latest_complete_week"] is not None
        assert health_payload["last_pipeline_run"]["trigger"] == "synthetic_demo"

        opportunities = client.get("/api/genres/opportunities")
        assert opportunities.status_code == 200
        opportunity_payload = opportunities.json()
        assert len(opportunity_payload) == len(DEMO_GENRES)
        assert {row["genre"] for row in opportunity_payload} == set(DEMO_GENRES)
        assert "afrobeat" in {row["genre"] for row in opportunity_payload}
        assert "classical" in {row["genre"] for row in opportunity_payload}
        assert "hip hop" in {row["genre"] for row in opportunity_payload}
        assert "latin music" in {row["genre"] for row in opportunity_payload}
        assert all(
            row["opportunity"]["lower"]
            <= row["opportunity"]["value"]
            <= row["opportunity"]["upper"]
            for row in opportunity_payload
        )

        genre = opportunity_payload[0]["genre"]
        timeseries = client.get(
            f"/api/genres/{genre}/timeseries",
            params={"weeks": 26},
        )
        assert timeseries.status_code == 200
        timeseries_payload = timeseries.json()
        assert len(timeseries_payload["history"]) == 10
        assert {row["target_axis"] for row in timeseries_payload["forecasts"]} == {
            "conversation",
            "listening",
        }

        evidence = client.get(
            f"/api/genres/{genre}/evidence",
            params={"week": health_payload["latest_complete_week"]},
        )
        assert evidence.status_code == 200
        evidence_payload = evidence.json()
        assert evidence_payload["bluesky_posts"]
        assert evidence_payload["lastfm_artists"]
        assert evidence_payload["musicbrainz_releases"]

        next_up = client.get("/api/forecast/next-up")
        assert next_up.status_code == 200
        assert next_up.json()
        assert {"skill", "no_skill"} <= {
            row["skill_status"] for row in next_up.json()
        }

        ecosystem = client.get("/api/ecosystem", params={"weeks": 26})
        assert ecosystem.status_code == 200
        assert len(ecosystem.json()) == 10
        assert ecosystem.json()[-1]["listening_entropy"] is not None

        briefs = client.get("/api/briefs")
        assert briefs.status_code == 200
        assert briefs.json()
        assert all(
            "Synthetic demo evidence" in row["rationale"]
            for row in briefs.json()
        )

        scene_map = client.get("/api/scene-map")
        assert scene_map.status_code == 200
        assert len(scene_map.json()) == len(DEMO_GENRES)
        assert all(row["opportunity"] is not None for row in scene_map.json())
