"""Build weekly metrics marts and print decision-ready latest-week summaries."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from soundcheck.metrics.models import (
    EcosystemWeekMetric,
    MetricsBatch,
)
from soundcheck.metrics.pipeline import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    build_metrics,
)
from soundcheck.metrics.scene_map import build_scene_map
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    load_taxonomy,
)

DEFAULT_CANONICAL_GENRES_PATH = DEFAULT_TAXONOMY_PATH


class MetricSettings(BaseModel):
    """Validated metrics batch settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    canonical_genres_path: Path = DEFAULT_CANONICAL_GENRES_PATH
    bootstrap_resamples: int = Field(
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
        gt=0,
    )


class RankingItem(BaseModel):
    """One uncertainty-bearing item in a printed ranking."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    estimate: float
    ci_low: float
    ci_high: float


class MetricRanking(BaseModel):
    """Latest-week top and bottom ranking for one decision metric."""

    model_config = ConfigDict(frozen=True)

    event: Literal["metric_ranking"] = "metric_ranking"
    metric: Literal["opportunity", "discovery_gap"]
    week_start: date | None
    status: Literal["ready", "unavailable"]
    top: tuple[RankingItem, ...]
    bottom: tuple[RankingItem, ...]


class EcosystemSummary(BaseModel):
    """Latest ecosystem-health row emitted by the batch."""

    model_config = ConfigDict(frozen=True)

    event: Literal["ecosystem_summary"] = "ecosystem_summary"
    status: Literal["ready", "unavailable"]
    row: EcosystemWeekMetric | None


class MetricsCompletion(BaseModel):
    """Validated terminal batch event."""

    model_config = ConfigDict(frozen=True)

    event: Literal["metrics_complete"] = "metrics_complete"
    genre_week_rows: int
    ecosystem_week_rows: int
    scene_map_rows: int
    bootstrap_resamples: int


class AxisOperationalSummary(BaseModel):
    """Source receipts, maturity states, and first decision-ready week."""

    model_config = ConfigDict(frozen=True)

    event: Literal["axis_operational_summary"] = "axis_operational_summary"
    artifact_family: Literal["v1"] = "v1"
    source_counts: dict[str, int]
    maturity_states: dict[str, int]
    first_eligible_complete_week: date | None


def _axis_summary(batch: MetricsBatch) -> AxisOperationalSummary:
    states: Counter[str] = Counter()
    for row in batch.axis_maturity:
        states[row.conversation_maturity] += 1
        states[row.listening_maturity] += 1
        states[row.supply_maturity] += 1
    complete_weeks = {
        row.week_start for row in batch.axis_maturity if row.decision_ready
    }
    return AxisOperationalSummary(
        source_counts={
            "bluesky_posts": len(batch.post_maturity),
            "bluesky_mature_posts": sum(
                row.engagement_maturity_status == "complete"
                for row in batch.post_maturity
            ),
            "lastfm_valid_artist_genre_weeks": sum(
                row.valid_listening_artist_count for row in batch.axis_maturity
            ),
            "musicbrainz_release_genre_weeks": sum(
                row.supply_release_group_count for row in batch.axis_maturity
            ),
        },
        maturity_states=dict(sorted(states.items())),
        first_eligible_complete_week=min(complete_weeks) if complete_weeks else None,
    )


async def async_main(settings: MetricSettings) -> MetricsBatch:
    """Load evidence, calculate all statistics, and replace both marts."""
    store = DuckDBMetricStore(settings.database_path)
    await store.initialize()
    metric_time = datetime.now(UTC)
    evidence = await store.load_evidence(as_of=metric_time)
    embeddings = await store.load_scene_embeddings()
    canonical_genres = load_taxonomy(
        settings.canonical_genres_path
    ).canonical_genres
    metrics_batch = await asyncio.to_thread(
        build_metrics,
        evidence,
        canonical_genres,
        computed_at=metric_time,
        bootstrap_resamples=settings.bootstrap_resamples,
    )
    scene_map_points = await asyncio.to_thread(
        build_scene_map,
        metrics_batch.genre_weeks,
        embeddings,
    )
    batch = MetricsBatch(
        genre_weeks=metrics_batch.genre_weeks,
        ecosystem_weeks=metrics_batch.ecosystem_weeks,
        scene_map_points=scene_map_points,
        axis_maturity=metrics_batch.axis_maturity,
        post_maturity=metrics_batch.post_maturity,
    )
    await store.replace_corrected(batch, evidence)
    return batch


def _ranking(
    batch: MetricsBatch,
    metric: Literal["opportunity", "discovery_gap"],
) -> MetricRanking:
    current_week = datetime.now(UTC).date()
    current_week -= timedelta(days=current_week.weekday())
    eligible_rows = tuple(
        row
        for row in batch.genre_weeks
        if row.week_start < current_week
        and (
            row.opportunity is not None
            if metric == "opportunity"
            else row.discovery_gap is not None
        )
    )
    if not eligible_rows:
        return MetricRanking(
            metric=metric,
            week_start=None,
            status="unavailable",
            top=(),
            bottom=(),
        )
    latest_week = max(row.week_start for row in eligible_rows)
    items: list[RankingItem] = []
    for row in eligible_rows:
        if row.week_start != latest_week:
            continue
        if metric == "opportunity":
            estimate = row.opportunity
            lower = row.opportunity_ci_low
            upper = row.opportunity_ci_high
        else:
            estimate = row.discovery_gap
            lower = row.discovery_gap_ci_low
            upper = row.discovery_gap_ci_high
        if estimate is None or lower is None or upper is None:
            continue
        items.append(
            RankingItem(
                canonical_genre=row.canonical_genre,
                estimate=estimate,
                ci_low=lower,
                ci_high=upper,
            )
        )
    items.sort(key=lambda item: (item.estimate, item.canonical_genre))
    return MetricRanking(
        metric=metric,
        week_start=latest_week,
        status="ready" if items else "unavailable",
        top=tuple(reversed(items[-10:])),
        bottom=tuple(items[:10]),
    )


def _ecosystem_summary(batch: MetricsBatch) -> EcosystemSummary:
    current_week = datetime.now(UTC).date()
    current_week -= timedelta(days=current_week.weekday())
    complete = tuple(
        row
        for row in batch.ecosystem_weeks
        if row.week_start < current_week and row.listening_observed_genres > 0
    )
    if not complete:
        return EcosystemSummary(status="unavailable", row=None)
    return EcosystemSummary(
        status="ready",
        row=max(complete, key=lambda row: row.week_start),
    )


def _emit(model: BaseModel) -> None:
    print(
        json.dumps(
            model.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument(
        "--canonical-genres",
        type=Path,
        default=DEFAULT_CANONICAL_GENRES_PATH,
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    settings = MetricSettings(
        database_path=args.database,
        canonical_genres_path=args.canonical_genres,
        bootstrap_resamples=args.bootstrap_resamples,
    )
    batch = asyncio.run(async_main(settings))
    _emit(_axis_summary(batch))
    _emit(_ranking(batch, "opportunity"))
    _emit(_ranking(batch, "discovery_gap"))
    _emit(_ecosystem_summary(batch))
    _emit(
        MetricsCompletion(
            genre_week_rows=len(batch.genre_weeks),
            ecosystem_week_rows=len(batch.ecosystem_weeks),
            scene_map_rows=len(batch.scene_map_points),
            bootstrap_resamples=settings.bootstrap_resamples,
        )
    )


if __name__ == "__main__":
    main()
