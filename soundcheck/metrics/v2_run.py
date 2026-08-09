"""Refresh coverage, build taxonomy-v2 metrics, and print honest rankings."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from soundcheck.metrics.coverage_run import (
    DEFAULT_THRESHOLDS_PATH,
    run_coverage,
)
from soundcheck.metrics.v2_models import MetricsV2Batch
from soundcheck.metrics.v2_pipeline import (
    DEFAULT_V2_BOOTSTRAP_RESAMPLES,
    build_metrics_v2,
)
from soundcheck.metrics.v2_storage import DuckDBMetricV2Store
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")


class MetricsV2Settings(BaseModel):
    """Validated v2 batch CLI settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_path: Path = DEFAULT_DATABASE_PATH
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    coverage_thresholds_path: Path = DEFAULT_THRESHOLDS_PATH
    bootstrap_resamples: int = Field(
        default=DEFAULT_V2_BOOTSTRAP_RESAMPLES,
        gt=0,
    )
    refresh_coverage: bool = True


class RankingItemV2(BaseModel):
    """One uncertainty-bearing opportunity row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre_id: str
    display_name: str
    macro_family_id: str
    estimate: float
    ci_low: float
    ci_high: float
    effective_n: float
    shrinkage_weight: float


class RankingV2(BaseModel):
    """Global or peer-family latest-week ranking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["metrics_v2_ranking"] = "metrics_v2_ranking"
    taxonomy_version: str
    context: Literal["global", "peer_family"]
    week_start: date | None
    status: Literal["ready", "unavailable"]
    top: tuple[RankingItemV2, ...]
    bottom: tuple[RankingItemV2, ...]


class CoverageStateSummary(BaseModel):
    """Latest-week eligibility counts printed with every run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["metrics_v2_coverage_states"] = "metrics_v2_coverage_states"
    taxonomy_version: str
    week_start: date | None
    states: dict[str, int]
    eligible_estimates: int


class MetricsV2Completion(BaseModel):
    """Terminal version-isolated batch summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["metrics_v2_complete"] = "metrics_v2_complete"
    taxonomy_version: str
    genre_week_rows: int
    macro_family_week_rows: int
    estimate_rows: int
    ecosystem_rows: int
    bootstrap_resamples: int


class AxisOperationalSummaryV2(BaseModel):
    """Version-isolated axis receipts and first complete week."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["axis_operational_summary_v2"] = "axis_operational_summary_v2"
    taxonomy_version: str
    source_counts: dict[str, int]
    maturity_states: dict[str, int]
    first_eligible_complete_week: date | None


def _axis_summary(batch: MetricsV2Batch) -> AxisOperationalSummaryV2:
    states: Counter[str] = Counter()
    for row in batch.axis_maturity:
        states[row.conversation_maturity] += 1
        states[row.listening_maturity] += 1
        states[row.supply_maturity] += 1
    complete_weeks = {
        row.week_start for row in batch.axis_maturity if row.decision_ready
    }
    return AxisOperationalSummaryV2(
        taxonomy_version=batch.taxonomy_version,
        source_counts={
            "bluesky_mature_post_genre_weeks": sum(
                row.mature_conversation_post_count for row in batch.axis_maturity
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


async def async_main(settings: MetricsV2Settings) -> MetricsV2Batch:
    """Refresh version-matched coverage and replace only this version's marts."""
    taxonomy = load_taxonomy(settings.taxonomy_path)
    computed_at = datetime.now(UTC)
    if settings.refresh_coverage:
        await asyncio.to_thread(
            run_coverage,
            database_path=settings.database_path,
            taxonomy_path=settings.taxonomy_path,
            thresholds_path=settings.coverage_thresholds_path,
            computed_at=computed_at,
        )
    store = DuckDBMetricV2Store(settings.database_path)
    await store.initialize()
    evidence = await store.load_evidence(
        taxonomy.taxonomy_version,
        as_of=computed_at,
    )
    batch = await asyncio.to_thread(
        build_metrics_v2,
        evidence,
        taxonomy,
        computed_at=computed_at,
        bootstrap_resamples=settings.bootstrap_resamples,
    )
    await store.replace_corrected(batch, evidence)
    return batch


def _ranking(
    batch: MetricsV2Batch,
    context: Literal["global", "peer_family"],
) -> RankingV2:
    current_week = datetime.now(UTC).date()
    current_week -= timedelta(days=current_week.weekday())
    opportunity_estimates = tuple(
        estimate
        for estimate in batch.estimates
        if estimate.week_start < current_week
        and estimate.scope_type == "genre"
        and estimate.context == context
        and estimate.metric_name == "opportunity"
        and estimate.estimate is not None
    )
    if not opportunity_estimates:
        return RankingV2(
            taxonomy_version=batch.taxonomy_version,
            context=context,
            week_start=None,
            status="unavailable",
            top=(),
            bottom=(),
        )
    latest_week = max(row.week_start for row in opportunity_estimates)
    genres = {
        row.genre_id: row
        for row in batch.genre_weeks
        if row.week_start == latest_week
    }
    items: list[RankingItemV2] = []
    for estimate in batch.estimates:
        if (
            estimate.week_start != latest_week
            or estimate.scope_type != "genre"
            or estimate.context != context
            or estimate.metric_name != "opportunity"
            or estimate.estimate is None
            or estimate.ci_low is None
            or estimate.ci_high is None
        ):
            continue
        genre = genres[estimate.scope_id]
        effective_n = min(
            value
            for value in (
                genre.conversation_effective_n,
                genre.listening_effective_n,
                genre.supply_effective_n,
            )
            if value is not None
        )
        shrinkage_weight = max(
            value
            for value in (
                genre.conversation_combined_shrinkage_weight,
                genre.listening_shrinkage_weight,
                genre.supply_combined_shrinkage_weight,
            )
            if value is not None
        )
        items.append(
            RankingItemV2(
                genre_id=genre.genre_id,
                display_name=genre.display_name,
                macro_family_id=genre.macro_family_id,
                estimate=estimate.estimate,
                ci_low=estimate.ci_low,
                ci_high=estimate.ci_high,
                effective_n=effective_n,
                shrinkage_weight=shrinkage_weight,
            )
        )
    items.sort(key=lambda item: (item.estimate, item.genre_id))
    return RankingV2(
        taxonomy_version=batch.taxonomy_version,
        context=context,
        week_start=latest_week,
        status="ready" if items else "unavailable",
        top=tuple(reversed(items[-10:])),
        bottom=tuple(items[:10]),
    )


def _coverage_summary(batch: MetricsV2Batch) -> CoverageStateSummary:
    if not batch.genre_weeks:
        return CoverageStateSummary(
            taxonomy_version=batch.taxonomy_version,
            week_start=None,
            states={},
            eligible_estimates=0,
        )
    latest_week = max(row.week_start for row in batch.genre_weeks)
    rows = tuple(
        row for row in batch.genre_weeks if row.week_start == latest_week
    )
    return CoverageStateSummary(
        taxonomy_version=batch.taxonomy_version,
        week_start=latest_week,
        states=dict(
            sorted(Counter(row.coverage_state for row in rows).items())
        ),
        eligible_estimates=sum(row.estimate_eligible for row in rows),
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
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument(
        "--coverage-thresholds",
        type=Path,
        default=DEFAULT_THRESHOLDS_PATH,
    )
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_V2_BOOTSTRAP_RESAMPLES,
    )
    parser.add_argument("--skip-coverage-refresh", action="store_true")
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    settings = MetricsV2Settings(
        database_path=args.database,
        taxonomy_path=args.taxonomy,
        coverage_thresholds_path=args.coverage_thresholds,
        bootstrap_resamples=args.bootstrap_resamples,
        refresh_coverage=not args.skip_coverage_refresh,
    )
    batch = asyncio.run(async_main(settings))
    _emit(_axis_summary(batch))
    _emit(_ranking(batch, "global"))
    _emit(_ranking(batch, "peer_family"))
    _emit(_coverage_summary(batch))
    _emit(
        MetricsV2Completion(
            taxonomy_version=batch.taxonomy_version,
            genre_week_rows=len(batch.genre_weeks),
            macro_family_week_rows=len(batch.macro_family_weeks),
            estimate_rows=len(batch.estimates),
            ecosystem_rows=len(batch.ecosystem_weeks),
            bootstrap_resamples=settings.bootstrap_resamples,
        )
    )


if __name__ == "__main__":
    main()
