"""Batch-only scene-map tests; serving never imports or runs UMAP."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from soundcheck.metrics.maturity import SupplyCollectionWindow
from soundcheck.metrics.models import (
    CanonicalGenreEmbedding,
    ConversationEvidence,
    ListeningDeltaCandidate,
    MetricEvidence,
)
from soundcheck.metrics.pipeline import build_metrics
from soundcheck.metrics.scene_map import build_scene_map


def test_scene_map_is_deterministic_and_carries_metric_uncertainty() -> None:
    genres = ("ambient", "breakcore", "jungle", "shoegaze", "slowcore")
    week = date(2026, 7, 13)
    evidence = MetricEvidence(
        conversation=tuple(
            ConversationEvidence(
                week_start=week,
                canonical_genre=genre,
                post_uri=f"at://post/{index}",
                mentions=1,
                likes=index,
                reposts=index,
                replies=0,
            )
            for index, genre in enumerate(genres)
        ),
        listening_candidates=tuple(
            ListeningDeltaCandidate(
                week_start=week,
                canonical_genre=genre,
                artist_key=f"name:artist-{index}",
                artist_name=f"Artist {index}",
                playcount=1_100 + 10 * index,
                listeners=110 + index,
                previous_playcount=1_000,
                previous_listeners=100,
                previous_fetched_at=datetime(2026, 7, 9, 12, tzinfo=UTC),
                fetched_at=datetime(2026, 7, 16, 12, tzinfo=UTC),
            )
            for index, genre in enumerate(genres)
        ),
        supply=(),
        supply_windows=(
            SupplyCollectionWindow(
                start_date=week,
                end_date=week + timedelta(days=6),
                completed_at=datetime(2026, 7, 20, tzinfo=UTC),
            ),
        ),
    )
    batch = build_metrics(
        evidence,
        genres,
        computed_at=datetime(2026, 7, 20, tzinfo=UTC),
        bootstrap_resamples=20,
        bootstrap_seed=4,
    )
    embeddings = tuple(
        CanonicalGenreEmbedding(
            canonical_genre=genre,
            embedding=(
                float(index == 0),
                float(index == 1),
                float(index == 2),
                float(index) / len(genres),
            ),
        )
        for index, genre in enumerate(genres)
    )

    first = build_scene_map(batch.genre_weeks, embeddings)
    second = build_scene_map(batch.genre_weeks, embeddings)

    assert len(first) == len(genres)
    assert [(row.x, row.y) for row in first] == pytest.approx(
        [(row.x, row.y) for row in second]
    )
    assert all(math.isfinite(row.x) and math.isfinite(row.y) for row in first)
    assert all(row.opportunity is not None for row in first)
    assert all(row.opportunity_ci_low is not None for row in first)
    assert all(row.opportunity_ci_high is not None for row in first)
    assert all(row.evidence_volume == 2 for row in first)
