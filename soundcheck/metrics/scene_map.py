"""Batch-only UMAP projection for the API scene map."""

from __future__ import annotations

import warnings
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
import umap  # type: ignore[import-untyped]

from soundcheck.metrics.models import (
    CanonicalGenreEmbedding,
    GenreWeekMetric,
    SceneMapPoint,
)

MIN_UMAP_GENRES = 3
UMAP_RANDOM_SEED = 20_260_724


def build_scene_map(
    genre_weeks: Sequence[GenreWeekMetric],
    embeddings: Sequence[CanonicalGenreEmbedding],
) -> tuple[SceneMapPoint, ...]:
    """Project embeddings once in the batch; the API only reads these rows."""
    if not genre_weeks:
        return ()
    latest_week = max(row.week_start for row in genre_weeks)
    latest_by_genre = {
        row.canonical_genre: row
        for row in genre_weeks
        if row.week_start == latest_week
    }
    selected = tuple(
        embedding
        for embedding in sorted(
            embeddings,
            key=lambda item: item.canonical_genre,
        )
        if embedding.canonical_genre in latest_by_genre
        and embedding.embedding
    )
    if len(selected) < MIN_UMAP_GENRES:
        return ()
    dimensions = {len(item.embedding) for item in selected}
    if len(dimensions) != 1:
        msg = "canonical genre embeddings must share one dimension"
        raise ValueError(msg)
    matrix = np.asarray(
        [item.embedding for item in selected],
        dtype=np.float64,
    )
    projection = _fit_umap(matrix)
    rows: list[SceneMapPoint] = []
    for embedding, coordinates in zip(selected, projection, strict=True):
        metric = latest_by_genre[embedding.canonical_genre]
        rows.append(
            SceneMapPoint(
                as_of_week=latest_week,
                canonical_genre=embedding.canonical_genre,
                x=float(coordinates[0]),
                y=float(coordinates[1]),
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
                computed_at=metric.computed_at,
            )
        )
    return tuple(rows)


def _fit_umap(
    matrix: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(15, len(matrix) - 1),
        min_dist=0.1,
        metric="cosine",
        init="random",
        random_state=UMAP_RANDOM_SEED,
        transform_seed=UMAP_RANDOM_SEED,
        n_jobs=1,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = reducer.fit_transform(matrix)
    return np.asarray(result, dtype=np.float64)
