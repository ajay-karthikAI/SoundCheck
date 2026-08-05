"""Compare taxonomy v1 and v2 artifacts and evaluate the documented cutover gates."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field

from soundcheck.ingest.scaling import (
    DEFAULT_SCALING_CONFIG_PATH,
    CollectionPlan,
    build_collection_plan,
)
from soundcheck.resolve.genres_v2 import (
    DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    load_resolution_v2_config,
)
from soundcheck.scripts.eval_resolution import (
    DEFAULT_EVAL_PATH,
    attach_current_predictions,
)
from soundcheck.scripts.eval_resolution import (
    evaluate_examples as evaluate_v1_resolution,
)
from soundcheck.scripts.eval_resolution import (
    load_examples as load_v1_examples,
)
from soundcheck.scripts.eval_resolution_v2 import (
    DEFAULT_EVAL_V2_PATH,
)
from soundcheck.scripts.eval_resolution_v2 import (
    evaluate_examples as evaluate_v2_resolution,
)
from soundcheck.scripts.eval_resolution_v2 import (
    load_examples as load_v2_examples,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    GenreTaxonomy,
    load_taxonomy,
    normalize_alias,
)

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
DEFAULT_CUTOVER_CONFIG_PATH = Path("config/taxonomy_v2_cutover.yml")


class ResolutionCutoverConfig(BaseModel):
    """Human-label quality floors for each macro family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_labeled_examples_per_family: int = Field(ge=1)
    minimum_precision: float = Field(ge=0.0, le=1.0)
    minimum_recall: float = Field(ge=0.0, le=1.0)
    minimum_mbid_precision: float = Field(ge=0.0, le=1.0)


class CoverageCutoverConfig(BaseModel):
    """Minimum family breadth and source overlap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_ready_enabled_genres_per_family: int = Field(ge=1)
    minimum_ready_enabled_genre_fraction: float = Field(ge=0.0, le=1.0)
    minimum_cross_source_overlap_rate: float = Field(ge=0.0, le=1.0)


class HistoryCutoverConfig(BaseModel):
    """Minimum valid weekly history for a family cutover."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_valid_metric_weeks: int = Field(ge=2)
    minimum_genres_with_history_per_family: int = Field(ge=1)


class MissingnessCutoverConfig(BaseModel):
    """Missing-evidence limits that never convert nulls into zeros."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_enabled_genre_missing_fraction: float = Field(ge=0.0, le=1.0)
    require_complete_ready_estimates: bool


class ForecastCutoverConfig(BaseModel):
    """Forecast validation requirements; no-skill remains publishable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_publishable_rows_per_family: int = Field(ge=1)
    minimum_empirical_interval_coverage_80: float = Field(ge=0.0, le=1.0)
    require_genre_and_family_validation: bool
    require_naive_baseline: bool


class AutomationCutoverConfig(BaseModel):
    """Runtime, recovery, and freshness limits for automated cutover."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_weekly_runtime_minutes: int = Field(ge=1)
    maximum_collection_shards_per_source: int = Field(ge=1)
    maximum_seconds_per_collection_shard: int = Field(ge=60)
    maximum_data_age_days: int = Field(ge=1)
    require_successful_weekly_manifest: bool


class TaxonomyCutoverConfig(BaseModel):
    """Version-matched cutover configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    resolution: ResolutionCutoverConfig
    coverage: CoverageCutoverConfig
    history: HistoryCutoverConfig
    missingness: MissingnessCutoverConfig
    forecast: ForecastCutoverConfig
    automation: AutomationCutoverConfig


class GateResult(BaseModel):
    """One explicit pass/fail release gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_id: str
    scope: str
    passed: bool
    observed: str
    threshold: str
    reason: str


class GenreCoverageComparison(BaseModel):
    """Latest v2 coverage for one versioned genre."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre_id: str
    display_name: str
    macro_family_id: str
    taxonomy_status: str
    eligibility_state: str
    cross_source_overlap: float | None
    valid_metric_weeks: int
    missing_axes: tuple[str, ...]
    latest_source_timestamp: datetime | None


class FamilyCoverageComparison(BaseModel):
    """Coverage, history, forecast, and activation state for one family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    macro_family_id: str
    display_name: str
    enabled_genres: int
    candidate_genres: int
    observed_genres: int
    ready_enabled_genres: int
    ready_fraction: float
    minimum_ready_overlap: float | None
    genres_with_minimum_history: int
    missing_enabled_genres: int
    missing_fraction: float
    publishable_forecast_rows: int
    invalid_publishable_forecast_rows: int
    resolution_status: str
    production_eligible: bool
    gates: tuple[GateResult, ...]


class MappingChange(BaseModel):
    """One source tag whose v2 mapping differs from the v1 compatibility map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_system: str
    source_tag: str
    v1_genre_ids: tuple[str, ...]
    v2_genre_ids: tuple[str, ...]
    v2_methods: tuple[str, ...]
    changed: bool
    v2_unresolved: bool


class UnresolvedComparison(BaseModel):
    """Explicit unresolved rate compared with the v1 `other` proxy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    v1_mapped_tags: int
    v1_other_tags: int
    v1_other_rate: float | None
    v2_mapped_tags: int
    v2_unresolved_tags: int
    v2_unresolved_rate: float | None


class MetricChange(BaseModel):
    """Latest common-week v1/v2 metric and ranking difference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre_id: str
    display_name: str
    metric_name: Literal["opportunity", "discovery_gap"]
    week_start: date
    v1_value: float | None
    v2_value: float | None
    value_change: float | None
    v1_rank: int | None
    v2_rank: int | None
    rank_change: int | None


class ForecastSkillChange(BaseModel):
    """Selected forecast status and validation difference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre_id: str
    target_axis: str
    horizon: int
    v1_status: str | None
    v1_model: str | None
    v1_mase: float | None
    v2_status: str | None
    v2_model: str | None
    v2_mase: float | None
    v2_family_mase: float | None
    changed: bool


class MissingnessChange(BaseModel):
    """Compatibility-genre missingness without zero filling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre_id: str
    display_name: str
    week_start: date
    v1_listening_missing: bool | None
    v1_opportunity_missing: bool | None
    v2_listening_missing: bool | None
    v2_opportunity_missing: bool | None
    changed: bool


class ResolutionQualityComparison(BaseModel):
    """Measured human-label status for both resolution layers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    v1_status: str
    v1_labeled_examples: int
    v1_precision: float | None
    v1_recall: float | None
    v2_status: str
    v2_labeled_examples: int
    v2_precision: float | None
    v2_recall: float | None
    v2_family_precision: dict[str, float | None]
    v2_family_recall: dict[str, float | None]


class AutomationComparison(BaseModel):
    """Collection-plan, pipeline-runtime, and freshness evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lastfm_shards: int
    lastfm_seconds_per_shard: float
    musicbrainz_shards: int
    musicbrainz_seconds_per_shard: float
    latest_weekly_run_id: str | None
    latest_weekly_run_status: str | None
    latest_weekly_runtime_seconds: float | None
    latest_source_timestamp: datetime | None
    gates: tuple[GateResult, ...]


class TaxonomyComparisonReport(BaseModel):
    """Complete comparison ledger and release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["taxonomy_version_comparison"] = "taxonomy_version_comparison"
    generated_at: datetime
    taxonomy_version: str
    database_path: str
    latest_coverage_week: date | None
    latest_common_metric_week: date | None
    genre_coverage: tuple[GenreCoverageComparison, ...]
    family_coverage: tuple[FamilyCoverageComparison, ...]
    changed_mappings: tuple[MappingChange, ...]
    unresolved: UnresolvedComparison
    resolution_quality: ResolutionQualityComparison
    metric_changes: tuple[MetricChange, ...]
    forecast_skill_changes: tuple[ForecastSkillChange, ...]
    missingness_changes: tuple[MissingnessChange, ...]
    automation: AutomationComparison
    global_gates: tuple[GateResult, ...]
    cutover_passed: bool
    failed_gate_count: int
    cutover_action: Literal["enable_v2_frontend", "hold_v1_frontend"]


def load_cutover_config(
    path: Path = DEFAULT_CUTOVER_CONFIG_PATH,
) -> TaxonomyCutoverConfig:
    """Load cutover thresholds through a strict Pydantic boundary."""

    return TaxonomyCutoverConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


def _query(
    connection: duckdb.DuckDBPyConnection,
    statement_name: str,
    parameters: Sequence[object] = (),
) -> tuple[tuple[object, ...], ...]:
    try:
        return tuple(
            connection.execute(
                load_sql(statement_name),
                list(parameters),
            ).fetchall()
        )
    except (duckdb.CatalogException, duckdb.BinderException):
        return ()


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _as_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _as_date(value: object) -> date:
    if not isinstance(value, date):
        raise TypeError("expected a DuckDB DATE value")
    return value


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _as_int(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("expected an integer value")
    return value


def _mapping_comparison(
    v1_rows: Sequence[tuple[object, ...]],
    v2_rows: Sequence[tuple[object, ...]],
    taxonomy: GenreTaxonomy,
) -> tuple[tuple[MappingChange, ...], UnresolvedComparison]:
    canonical_to_id = {
        genre.canonical_name: genre.genre_id for genre in taxonomy.genres
    }
    v1: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw_labels: dict[tuple[str, str], str] = {}
    v1_other = 0
    for source, raw_tag, canonical, _method, _similarity in v1_rows:
        key = (str(source), normalize_alias(str(raw_tag)))
        raw_labels.setdefault(key, str(raw_tag))
        canonical_name = str(canonical).casefold()
        target = canonical_to_id.get(canonical_name)
        if target is not None:
            v1[key].add(target)
        if canonical_name == "other":
            v1_other += 1

    v2: dict[tuple[str, str], set[str]] = defaultdict(set)
    methods: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (
        source,
        source_tag,
        normalized_tag,
        genre_id,
        _family_id,
        method,
        _confidence,
        _weight,
    ) in v2_rows:
        key = (str(source), str(normalized_tag))
        raw_labels.setdefault(key, str(source_tag))
        v2[key].add(str(genre_id))
        methods[key].add(str(method))

    unresolved_id = taxonomy.unresolved_genre_id
    changes = []
    for key in sorted(set(v1) | set(v2)):
        v1_ids = tuple(sorted(v1.get(key, set())))
        v2_ids = tuple(sorted(v2.get(key, set())))
        resolved_v2_ids = tuple(
            genre_id for genre_id in v2_ids if genre_id != unresolved_id
        )
        changes.append(
            MappingChange(
                source_system=key[0],
                source_tag=raw_labels.get(key, key[1]),
                v1_genre_ids=v1_ids,
                v2_genre_ids=v2_ids,
                v2_methods=tuple(sorted(methods.get(key, set()))),
                changed=v1_ids != resolved_v2_ids,
                v2_unresolved=bool(v2_ids) and not resolved_v2_ids,
            )
        )
    v2_tag_count = len(v2)
    unresolved_count = sum(
        bool(targets) and targets <= {unresolved_id}
        for targets in v2.values()
    )
    summary = UnresolvedComparison(
        v1_mapped_tags=len(v1),
        v1_other_tags=v1_other,
        v1_other_rate=(
            v1_other / len(v1) if v1 else None
        ),
        v2_mapped_tags=v2_tag_count,
        v2_unresolved_tags=unresolved_count,
        v2_unresolved_rate=(
            unresolved_count / v2_tag_count if v2_tag_count else None
        ),
    )
    return tuple(change for change in changes if change.changed), summary


def _resolution_quality(
    database_path: Path,
    taxonomy: GenreTaxonomy,
) -> tuple[ResolutionQualityComparison, dict[str, object]]:
    v1_report = evaluate_v1_resolution(
        attach_current_predictions(
            load_v1_examples(DEFAULT_EVAL_PATH),
            database_path,
        )
    )
    resolution_config = load_resolution_v2_config(
        DEFAULT_RESOLUTION_V2_CONFIG_PATH
    )
    v2_report = evaluate_v2_resolution(
        load_v2_examples(DEFAULT_EVAL_V2_PATH),
        taxonomy,
        resolution_config.activation,
    )
    quality = ResolutionQualityComparison(
        v1_status=v1_report.status,
        v1_labeled_examples=v1_report.labeled_examples,
        v1_precision=(
            v1_report.overall.precision if v1_report.overall else None
        ),
        v1_recall=(
            v1_report.overall.recall if v1_report.overall else None
        ),
        v2_status=v2_report.status,
        v2_labeled_examples=v2_report.labeled_examples,
        v2_precision=(
            v2_report.overall.precision if v2_report.overall else None
        ),
        v2_recall=v2_report.overall.recall if v2_report.overall else None,
        v2_family_precision={
            family_id: (
                metrics.precision if metrics is not None else None
            )
            for family_id, metrics in (
                (
                    family.macro_family_id,
                    v2_report.by_macro_family.get(
                        family.macro_family_id
                    ),
                )
                for family in taxonomy.macro_families
            )
        },
        v2_family_recall={
            family_id: (
                metrics.recall if metrics is not None else None
            )
            for family_id, metrics in (
                (
                    family.macro_family_id,
                    v2_report.by_macro_family.get(
                        family.macro_family_id
                    ),
                )
                for family in taxonomy.macro_families
            )
        },
    )
    return quality, {
        family_id: activation
        for family_id, activation in v2_report.family_activation.items()
    }


def _coverage_rows(
    rows: Sequence[tuple[object, ...]],
    history_rows: Sequence[tuple[object, ...]],
) -> tuple[date | None, tuple[GenreCoverageComparison, ...]]:
    history = {
        str(row[0]): _as_int(row[2])
        for row in history_rows
    }
    coverage = []
    latest_week: date | None = None
    for row in rows:
        week = _as_date(row[0])
        latest_week = week
        missing_axes = tuple(
            axis
            for axis, missing in (
                ("listening", bool(row[8])),
                ("conversation", bool(row[9])),
                ("supply", bool(row[10])),
            )
            if missing
        )
        coverage.append(
            GenreCoverageComparison(
                genre_id=str(row[1]),
                display_name=str(row[2]),
                macro_family_id=str(row[3]),
                taxonomy_status=str(row[5]),
                eligibility_state=str(row[6]),
                cross_source_overlap=_as_float(row[7]),
                valid_metric_weeks=history.get(str(row[1]), 0),
                missing_axes=missing_axes,
                latest_source_timestamp=_as_datetime(row[11]),
            )
        )
    return latest_week, tuple(coverage)


def _rank(values: dict[str, float]) -> dict[str, int]:
    return {
        genre_id: index
        for index, (genre_id, _value) in enumerate(
            sorted(
                values.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            start=1,
        )
    }


def _metric_changes(
    v1_rows: Sequence[tuple[object, ...]],
    v2_rows: Sequence[tuple[object, ...]],
    taxonomy: GenreTaxonomy,
) -> tuple[date | None, tuple[MetricChange, ...], tuple[MissingnessChange, ...]]:
    canonical_to_id = {
        genre.canonical_name: genre.genre_id for genre in taxonomy.genres
    }
    names = {
        genre.genre_id: genre.display_name for genre in taxonomy.genres
    }
    v1_metrics: dict[tuple[date, str, str], float | None] = {}
    v1_missing: dict[tuple[date, str], tuple[bool, bool]] = {}
    for week_value, canonical, opportunity, gap, listen_missing, opp_missing in v1_rows:
        genre_id = canonical_to_id.get(str(canonical).casefold())
        if genre_id is None:
            continue
        week = _as_date(week_value)
        v1_metrics[(week, genre_id, "opportunity")] = _as_float(opportunity)
        v1_metrics[(week, genre_id, "discovery_gap")] = _as_float(gap)
        v1_missing[(week, genre_id)] = (
            bool(listen_missing),
            bool(opp_missing),
        )
    v2_metrics: dict[tuple[date, str, str], tuple[float | None, float | None, float | None]] = {}
    for week_value, row_genre_id, metric, estimate, low, high, _status in v2_rows:
        v2_metrics[(_as_date(week_value), str(row_genre_id), str(metric))] = (
            _as_float(estimate),
            _as_float(low),
            _as_float(high),
        )
    common_weeks = {
        key[0] for key in v1_metrics
    } & {
        key[0] for key in v2_metrics
    }
    if not common_weeks:
        return None, (), ()
    week = max(common_weeks)
    changes = []
    for metric_name in ("opportunity", "discovery_gap"):
        v1_values = {
            genre_id: value
            for (row_week, genre_id, metric), value in v1_metrics.items()
            if row_week == week and metric == metric_name and value is not None
        }
        v2_values = {
            genre_id: values[0]
            for (row_week, genre_id, metric), values in v2_metrics.items()
            if
            row_week == week
            and metric == metric_name
            and values[0] is not None
        }
        v2_finite = {
            genre_id: value
            for genre_id, value in v2_values.items()
            if value is not None
        }
        v1_ranks = _rank(v1_values)
        v2_ranks = _rank(v2_finite)
        for genre_id in sorted(set(v1_values) | set(v2_finite)):
            v1_value = v1_values.get(genre_id)
            v2_value = v2_finite.get(genre_id)
            v1_rank = v1_ranks.get(genre_id)
            v2_rank = v2_ranks.get(genre_id)
            changes.append(
                MetricChange(
                    genre_id=genre_id,
                    display_name=names.get(genre_id, genre_id),
                    metric_name=metric_name,
                    week_start=week,
                    v1_value=v1_value,
                    v2_value=v2_value,
                    value_change=(
                        v2_value - v1_value
                        if v1_value is not None and v2_value is not None
                        else None
                    ),
                    v1_rank=v1_rank,
                    v2_rank=v2_rank,
                    rank_change=(
                        v2_rank - v1_rank
                        if v1_rank is not None and v2_rank is not None
                        else None
                    ),
                )
            )
    missingness = []
    compatibility_ids = set(
        taxonomy.production_compatibility.canonical_genre_ids
    )
    for genre_id in sorted(compatibility_ids):
        v1_state = v1_missing.get((week, genre_id))
        listening_metric = v2_metrics.get((week, genre_id, "listening"))
        opportunity_metric = v2_metrics.get((week, genre_id, "opportunity"))
        v2_listening_missing = (
            listening_metric[0] is None if listening_metric else None
        )
        v2_opportunity_missing = (
            opportunity_metric[0] is None if opportunity_metric else None
        )
        if v1_state is None and listening_metric is None and opportunity_metric is None:
            continue
        v1_listening_missing = v1_state[0] if v1_state else None
        v1_opportunity_missing = v1_state[1] if v1_state else None
        missingness.append(
            MissingnessChange(
                genre_id=genre_id,
                display_name=names.get(genre_id, genre_id),
                week_start=week,
                v1_listening_missing=v1_listening_missing,
                v1_opportunity_missing=v1_opportunity_missing,
                v2_listening_missing=v2_listening_missing,
                v2_opportunity_missing=v2_opportunity_missing,
                changed=(
                    v1_listening_missing != v2_listening_missing
                    or v1_opportunity_missing != v2_opportunity_missing
                ),
            )
        )
    return week, tuple(changes), tuple(missingness)


def _forecast_changes(
    v1_rows: Sequence[tuple[object, ...]],
    v2_rows: Sequence[tuple[object, ...]],
    taxonomy: GenreTaxonomy,
) -> tuple[ForecastSkillChange, ...]:
    canonical_to_id = {
        genre.canonical_name: genre.genre_id for genre in taxonomy.genres
    }
    v1: dict[tuple[str, str, int], tuple[str, str, float | None]] = {}
    for (
        canonical,
        axis,
        horizon,
        model,
        is_naive,
        status,
        mase,
        _coverage,
        _target_week,
    ) in v1_rows:
        genre_id = canonical_to_id.get(str(canonical).casefold())
        if genre_id is None:
            continue
        key = (genre_id, str(axis), _as_int(horizon))
        candidate = (str(status), str(model), _as_float(mase))
        if not bool(is_naive) or key not in v1:
            v1[key] = candidate
    v2: dict[tuple[str, str, int], tuple[str, str | None, float | None, float | None]] = {}
    for row in v2_rows:
        if str(row[2]) != "global":
            continue
        key = (str(row[0]), str(row[3]), _as_int(row[4]))
        v2[key] = (
            str(row[5]),
            str(row[6]) if row[6] is not None else None,
            _as_float(row[10]),
            _as_float(row[12]),
        )
    changes = []
    for key in sorted(set(v1) | set(v2)):
        v1_value = v1.get(key)
        v2_value = v2.get(key)
        changes.append(
            ForecastSkillChange(
                genre_id=key[0],
                target_axis=key[1],
                horizon=key[2],
                v1_status=v1_value[0] if v1_value else None,
                v1_model=v1_value[1] if v1_value else None,
                v1_mase=v1_value[2] if v1_value else None,
                v2_status=v2_value[0] if v2_value else None,
                v2_model=v2_value[1] if v2_value else None,
                v2_mase=v2_value[2] if v2_value else None,
                v2_family_mase=v2_value[3] if v2_value else None,
                changed=(
                    v1_value is None
                    or v2_value is None
                    or v1_value[0] != v2_value[0]
                    or v1_value[1] != v2_value[1]
                    or v1_value[2] != v2_value[2]
                ),
            )
        )
    return tuple(changes)


def _valid_forecast_row(
    row: tuple[object, ...],
    config: ForecastCutoverConfig,
) -> bool:
    status = str(row[5])
    if status not in {"ready", "no_skill"}:
        return False
    point = _as_float(row[7])
    low = _as_float(row[8])
    high = _as_float(row[9])
    if point is None or low is None or high is None or not low <= point <= high:
        return False
    genre_mase = _as_float(row[10])
    genre_coverage = _as_float(row[11])
    family_mase = _as_float(row[12])
    family_coverage = _as_float(row[13])
    if config.require_genre_and_family_validation and (
        genre_mase is None
        or genre_coverage is None
        or family_mase is None
        or family_coverage is None
    ):
        return False
    if genre_coverage is not None and (
        genre_coverage < config.minimum_empirical_interval_coverage_80
    ):
        return False
    if family_coverage is not None and (
        family_coverage < config.minimum_empirical_interval_coverage_80
    ):
        return False
    if config.require_naive_baseline:
        naive_point = _as_float(row[14])
        naive_low = _as_float(row[15])
        naive_high = _as_float(row[16])
        if (
            naive_point is None
            or naive_low is None
            or naive_high is None
            or not naive_low <= naive_point <= naive_high
        ):
            return False
    return True


def _gate(
    gate_id: str,
    scope: str,
    passed: bool,
    observed: str,
    threshold: str,
    reason: str,
) -> GateResult:
    return GateResult(
        gate_id=gate_id,
        scope=scope,
        passed=passed,
        observed=observed,
        threshold=threshold,
        reason=reason,
    )


def _family_coverage(
    taxonomy: GenreTaxonomy,
    coverage: Sequence[GenreCoverageComparison],
    forecast_rows: Sequence[tuple[object, ...]],
    metric_rows: Sequence[tuple[object, ...]],
    activations: dict[str, object],
    config: TaxonomyCutoverConfig,
) -> tuple[FamilyCoverageComparison, ...]:
    coverage_by_id = {row.genre_id: row for row in coverage}
    latest_metric_week = max(
        (_as_date(row[0]) for row in metric_rows),
        default=None,
    )
    ready_metric_keys = {
        (str(row[1]), str(row[2]))
        for row in metric_rows
        if
        (latest_metric_week is not None and _as_date(row[0]) == latest_metric_week)
        and _as_float(row[3]) is not None
        and _as_float(row[4]) is not None
        and _as_float(row[5]) is not None
    }
    family_reports = []
    family_names = {
        family.macro_family_id: family.display_name
        for family in taxonomy.macro_families
    }
    for family_id, display_name in sorted(family_names.items()):
        enabled = tuple(
            genre
            for genre in taxonomy.genres
            if genre.macro_family_id == family_id
            and genre.status == "enabled"
            and genre.genre_id
            not in {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
        )
        candidates = tuple(
            genre
            for genre in taxonomy.genres
            if genre.macro_family_id == family_id
            and genre.status == "candidate"
            and genre.genre_id
            not in {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
        )
        if not enabled:
            observed = sum(
                genre.genre_id in coverage_by_id for genre in candidates
            )
            family_reports.append(
                FamilyCoverageComparison(
                    macro_family_id=family_id,
                    display_name=display_name,
                    enabled_genres=0,
                    candidate_genres=len(candidates),
                    observed_genres=observed,
                    ready_enabled_genres=0,
                    ready_fraction=0.0,
                    minimum_ready_overlap=None,
                    genres_with_minimum_history=0,
                    missing_enabled_genres=0,
                    missing_fraction=0.0,
                    publishable_forecast_rows=0,
                    invalid_publishable_forecast_rows=0,
                    resolution_status="candidate",
                    production_eligible=False,
                    gates=(),
                )
            )
            continue
        rows = tuple(
            coverage_by_id[genre.genre_id]
            for genre in enabled
            if genre.genre_id in coverage_by_id
        )
        ready = tuple(
            row for row in rows if row.eligibility_state == "ready"
        )
        ready_fraction = _ratio(len(ready), len(enabled))
        overlaps = tuple(
            row.cross_source_overlap
            for row in ready
            if row.cross_source_overlap is not None
        )
        history_count = sum(
            row.valid_metric_weeks
            >= config.history.minimum_valid_metric_weeks
            for row in ready
        )
        missing_count = len(enabled) - len(ready)
        missing_fraction = _ratio(missing_count, len(enabled))
        family_forecasts = tuple(
            row
            for row in forecast_rows
            if str(row[1]) == family_id
        )
        publishable = tuple(
            row
            for row in family_forecasts
            if str(row[5]) in {"ready", "no_skill"}
        )
        invalid_publishable = sum(
            not _valid_forecast_row(row, config.forecast)
            for row in publishable
        )
        activation = activations.get(family_id)
        production_eligible = bool(
            getattr(activation, "production_eligible", False)
        )
        activation_status = str(
            getattr(activation, "status", "candidate")
        )
        resolution_gate = _gate(
            "resolution_quality",
            family_id,
            production_eligible,
            (
                f"status={activation_status}; "
                f"labels={getattr(activation, 'labeled_examples', 0)}; "
                f"precision={getattr(activation, 'precision', None)}; "
                f"recall={getattr(activation, 'recall', None)}; "
                f"mbid_precision={getattr(activation, 'mbid_precision', None)}"
            ),
            (
                f"labels>={config.resolution.minimum_labeled_examples_per_family}, "
                f"precision>={config.resolution.minimum_precision:.2f}, "
                f"recall>={config.resolution.minimum_recall:.2f}, "
                f"mbid_precision>={config.resolution.minimum_mbid_precision:.2f}"
            ),
            (
                "Human-labeled resolution thresholds pass."
                if production_eligible
                else "Family remains candidate until human-labeled resolution passes."
            ),
        )
        coverage_passed = (
            len(ready)
            >= config.coverage.minimum_ready_enabled_genres_per_family
            and ready_fraction
            >= config.coverage.minimum_ready_enabled_genre_fraction
            and bool(overlaps)
            and min(overlaps)
            >= config.coverage.minimum_cross_source_overlap_rate
        )
        coverage_gate = _gate(
            "cross_source_coverage",
            family_id,
            coverage_passed,
            (
                f"ready={len(ready)}/{len(enabled)} "
                f"({ready_fraction:.1%}); "
                f"minimum_overlap={min(overlaps) if overlaps else None}"
            ),
            (
                f"ready>={config.coverage.minimum_ready_enabled_genres_per_family}; "
                f"fraction>={config.coverage.minimum_ready_enabled_genre_fraction:.0%}; "
                f"overlap>={config.coverage.minimum_cross_source_overlap_rate:.0%}"
            ),
            (
                "Cross-source family coverage passes."
                if coverage_passed
                else "Too few enabled genres clear every source-coverage gate."
            ),
        )
        history_passed = (
            history_count
            >= config.history.minimum_genres_with_history_per_family
        )
        history_gate = _gate(
            "minimum_history",
            family_id,
            history_passed,
            f"{history_count} ready genres have minimum history",
            (
                f">={config.history.minimum_genres_with_history_per_family} genres "
                f"with >={config.history.minimum_valid_metric_weeks} valid weeks"
            ),
            (
                "Forecast history passes."
                if history_passed
                else "The family is still accumulating valid weekly deltas."
            ),
        )
        complete_ready_estimates = all(
            all(
                (row.genre_id, metric_name) in ready_metric_keys
                for metric_name in (
                    "conversation",
                    "listening",
                    "supply",
                    "opportunity",
                    "discovery_gap",
                )
            )
            for row in ready
        )
        missingness_passed = (
            missing_fraction
            <= config.missingness.maximum_enabled_genre_missing_fraction
            and (
                complete_ready_estimates
                or not config.missingness.require_complete_ready_estimates
            )
        )
        missingness_gate = _gate(
            "acceptable_missingness",
            family_id,
            missingness_passed,
            (
                f"missing={missing_count}/{len(enabled)} "
                f"({missing_fraction:.1%}); "
                f"ready_estimates_complete={complete_ready_estimates}"
            ),
            (
                f"missing<={config.missingness.maximum_enabled_genre_missing_fraction:.0%}; "
                "ready estimates must include intervals"
            ),
            (
                "Missingness is explicit and within the cutover limit."
                if missingness_passed
                else "Missing evidence exceeds the family cutover limit."
            ),
        )
        forecast_passed = (
            len(publishable)
            >= config.forecast.minimum_publishable_rows_per_family
            and invalid_publishable == 0
        )
        forecast_gate = _gate(
            "forecast_validation",
            family_id,
            forecast_passed,
            (
                f"publishable={len(publishable)}; "
                f"invalid_publishable={invalid_publishable}"
            ),
            (
                f">={config.forecast.minimum_publishable_rows_per_family} rows; "
                "genre/family validation, intervals, and naive baseline required"
            ),
            (
                "Forecast validation passes; no-skill rows remain valid outcomes."
                if forecast_passed
                else "The family lacks enough fully validated forecast rows."
            ),
        )
        gates = (
            resolution_gate,
            coverage_gate,
            history_gate,
            missingness_gate,
            forecast_gate,
        )
        family_reports.append(
            FamilyCoverageComparison(
                macro_family_id=family_id,
                display_name=display_name,
                enabled_genres=len(enabled),
                candidate_genres=len(candidates),
                observed_genres=len(rows),
                ready_enabled_genres=len(ready),
                ready_fraction=ready_fraction,
                minimum_ready_overlap=min(overlaps) if overlaps else None,
                genres_with_minimum_history=history_count,
                missing_enabled_genres=missing_count,
                missing_fraction=missing_fraction,
                publishable_forecast_rows=len(publishable),
                invalid_publishable_forecast_rows=invalid_publishable,
                resolution_status=activation_status,
                production_eligible=all(gate.passed for gate in gates),
                gates=gates,
            )
        )
    return tuple(family_reports)


def _automation_comparison(
    plan: CollectionPlan,
    pipeline_rows: Sequence[tuple[object, ...]],
    coverage: Sequence[GenreCoverageComparison],
    config: AutomationCutoverConfig,
    *,
    generated_at: datetime,
) -> AutomationComparison:
    pipeline = pipeline_rows[0] if pipeline_rows else None
    run_id = str(pipeline[0]) if pipeline else None
    run_status = str(pipeline[1]) if pipeline else None
    runtime = _as_float(pipeline[4]) if pipeline else None
    latest_source = max(
        (
            row.latest_source_timestamp
            for row in coverage
            if row.latest_source_timestamp is not None
        ),
        default=None,
    )
    runtime_passed = (
        runtime is not None
        and runtime
        <= config.maximum_weekly_runtime_minutes * 60
        and (
            run_status == "success"
            or not config.require_successful_weekly_manifest
        )
    )
    shard_passed = (
        plan.lastfm.shard_count
        <= config.maximum_collection_shards_per_source
        and plan.musicbrainz.shard_count
        <= config.maximum_collection_shards_per_source
        and plan.lastfm.estimated_seconds_per_shard
        <= config.maximum_seconds_per_collection_shard
        and plan.musicbrainz.estimated_seconds_per_shard
        <= config.maximum_seconds_per_collection_shard
    )
    freshness_days = (
        (generated_at - latest_source).total_seconds() / 86_400
        if latest_source is not None
        else None
    )
    freshness_passed = (
        freshness_days is not None
        and freshness_days <= config.maximum_data_age_days
    )
    gates = (
        _gate(
            "weekly_runtime",
            "global",
            runtime_passed,
            f"status={run_status}; runtime_seconds={runtime}",
            (
                f"successful weekly manifest and "
                f"runtime<={config.maximum_weekly_runtime_minutes} minutes"
            ),
            (
                "Observed automation runtime passes."
                if runtime_passed
                else "No successful in-limit weekly manifest is available."
            ),
        ),
        _gate(
            "collection_recovery_plan",
            "global",
            shard_passed,
            (
                f"Last.fm={plan.lastfm.shard_count} shards/"
                f"{plan.lastfm.estimated_seconds_per_shard:.0f}s; "
                f"MusicBrainz={plan.musicbrainz.shard_count} shards/"
                f"{plan.musicbrainz.estimated_seconds_per_shard:.0f}s"
            ),
            (
                f"<={config.maximum_collection_shards_per_source} shards/source; "
                f"<={config.maximum_seconds_per_collection_shard}s/shard"
            ),
            (
                "Deterministic resumable shards fit the configured window."
                if shard_passed
                else "The dry-run plan exceeds the recoverable collection window."
            ),
        ),
        _gate(
            "data_freshness",
            "global",
            freshness_passed,
            f"latest_source={latest_source}; age_days={freshness_days}",
            f"age<={config.maximum_data_age_days} days",
            (
                "Source evidence is fresh."
                if freshness_passed
                else "The latest source evidence is stale or unavailable."
            ),
        ),
    )
    return AutomationComparison(
        lastfm_shards=plan.lastfm.shard_count,
        lastfm_seconds_per_shard=plan.lastfm.estimated_seconds_per_shard,
        musicbrainz_shards=plan.musicbrainz.shard_count,
        musicbrainz_seconds_per_shard=plan.musicbrainz.estimated_seconds_per_shard,
        latest_weekly_run_id=run_id,
        latest_weekly_run_status=run_status,
        latest_weekly_runtime_seconds=runtime,
        latest_source_timestamp=latest_source,
        gates=gates,
    )


def build_comparison_report(
    *,
    database_path: Path,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    cutover_config_path: Path = DEFAULT_CUTOVER_CONFIG_PATH,
    scaling_config_path: Path = DEFAULT_SCALING_CONFIG_PATH,
    generated_at: datetime | None = None,
) -> TaxonomyComparisonReport:
    """Build a read-only comparison and fail closed when evidence is absent."""

    if not database_path.exists():
        raise FileNotFoundError(database_path)
    now = (generated_at or datetime.now(UTC)).astimezone(UTC)
    taxonomy = load_taxonomy(taxonomy_path)
    config = load_cutover_config(cutover_config_path)
    if taxonomy.taxonomy_version != config.taxonomy_version:
        raise ValueError("cutover and taxonomy versions must match")
    plan = build_collection_plan(
        database_path=database_path,
        taxonomy_path=taxonomy_path,
        config_path=scaling_config_path,
        as_of=now.date(),
        generated_at=now,
    )
    with duckdb.connect(str(database_path), read_only=True) as connection:
        v1_mapping_rows = _query(
            connection,
            "compare_v1_tag_mappings.sql",
        )
        v2_mapping_rows = _query(
            connection,
            "compare_v2_tag_mappings.sql",
            (taxonomy.taxonomy_version,),
        )
        coverage_rows = _query(
            connection,
            "compare_v2_latest_coverage.sql",
            (taxonomy.taxonomy_version, taxonomy.taxonomy_version),
        )
        history_rows = _query(
            connection,
            "compare_v2_genre_history.sql",
            (taxonomy.taxonomy_version,),
        )
        v1_metric_rows = _query(connection, "compare_v1_metrics.sql")
        v2_metric_rows = _query(
            connection,
            "compare_v2_metrics.sql",
            (taxonomy.taxonomy_version,),
        )
        v1_forecast_rows = _query(
            connection,
            "compare_v1_forecasts.sql",
        )
        v2_forecast_rows = _query(
            connection,
            "compare_v2_forecasts.sql",
            (taxonomy.taxonomy_version,),
        )
        pipeline_rows = _query(
            connection,
            "compare_latest_pipeline_run.sql",
        )

    changed_mappings, unresolved = _mapping_comparison(
        v1_mapping_rows,
        v2_mapping_rows,
        taxonomy,
    )
    resolution_quality, activations = _resolution_quality(
        database_path,
        taxonomy,
    )
    latest_coverage_week, genre_coverage = _coverage_rows(
        coverage_rows,
        history_rows,
    )
    latest_common_week, metric_changes, missingness_changes = _metric_changes(
        v1_metric_rows,
        v2_metric_rows,
        taxonomy,
    )
    forecast_changes = _forecast_changes(
        v1_forecast_rows,
        v2_forecast_rows,
        taxonomy,
    )
    family_coverage = _family_coverage(
        taxonomy,
        genre_coverage,
        v2_forecast_rows,
        v2_metric_rows,
        activations,
        config,
    )
    automation = _automation_comparison(
        plan,
        pipeline_rows,
        genre_coverage,
        config.automation,
        generated_at=now,
    )
    family_gates = tuple(
        gate
        for family in family_coverage
        for gate in family.gates
    )
    global_gates = automation.gates
    failed_gate_count = sum(
        not gate.passed for gate in (*family_gates, *global_gates)
    )
    cutover_passed = bool(family_coverage) and failed_gate_count == 0
    return TaxonomyComparisonReport(
        generated_at=now,
        taxonomy_version=taxonomy.taxonomy_version,
        database_path=str(database_path),
        latest_coverage_week=latest_coverage_week,
        latest_common_metric_week=latest_common_week,
        genre_coverage=genre_coverage,
        family_coverage=family_coverage,
        changed_mappings=changed_mappings,
        unresolved=unresolved,
        resolution_quality=resolution_quality,
        metric_changes=metric_changes,
        forecast_skill_changes=forecast_changes,
        missingness_changes=missingness_changes,
        automation=automation,
        global_gates=global_gates,
        cutover_passed=cutover_passed,
        failed_gate_count=failed_gate_count,
        cutover_action=(
            "enable_v2_frontend"
            if cutover_passed
            else "hold_v1_frontend"
        ),
    )


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    return str(value)


def _table(
    headers: tuple[str, ...],
    rows: Iterable[tuple[object, ...]],
) -> str:
    rendered = [tuple(_display(value) for value in row) for row in rows]
    if not rendered:
        return "(none)"
    widths = [
        max(header.__len__(), *(row[index].__len__() for row in rendered))
        for index, header in enumerate(headers)
    ]
    lines = [
        "  ".join(
            header.ljust(widths[index])
            for index, header in enumerate(headers)
        ),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        )
        for row in rendered
    )
    return "\n".join(lines)


def render_report(report: TaxonomyComparisonReport) -> str:
    """Render a readable comparison and complete pass/fail checklist."""

    coverage_table = _table(
        (
            "genre",
            "family",
            "taxonomy",
            "coverage",
            "overlap",
            "valid weeks",
            "missing axes",
        ),
        (
            (
                row.display_name,
                row.macro_family_id,
                row.taxonomy_status,
                row.eligibility_state,
                row.cross_source_overlap,
                row.valid_metric_weeks,
                ",".join(row.missing_axes) or "none",
            )
            for row in report.genre_coverage
        ),
    )
    family_table = _table(
        (
            "family",
            "enabled/candidate",
            "observed",
            "ready enabled",
            "ready %",
            "history",
            "missing %",
            "forecasts",
            "activation",
            "cutover",
        ),
        (
            (
                row.display_name,
                f"{row.enabled_genres}/{row.candidate_genres}",
                row.observed_genres,
                f"{row.ready_enabled_genres}/{row.enabled_genres}",
                row.ready_fraction,
                row.genres_with_minimum_history,
                row.missing_fraction,
                row.publishable_forecast_rows,
                row.resolution_status,
                row.production_eligible,
            )
            for row in report.family_coverage
        ),
    )
    mapping_table = _table(
        ("source", "tag", "v1", "v2", "unresolved"),
        (
            (
                row.source_system,
                row.source_tag,
                ",".join(row.v1_genre_ids) or "none",
                ",".join(row.v2_genre_ids) or "none",
                row.v2_unresolved,
            )
            for row in report.changed_mappings
        ),
    )
    opportunity_table = _table(
        ("genre", "v1 rank", "v2 rank", "rank Δ", "v1", "v2", "value Δ"),
        (
            (
                row.display_name,
                row.v1_rank,
                row.v2_rank,
                row.rank_change,
                row.v1_value,
                row.v2_value,
                row.value_change,
            )
            for row in report.metric_changes
            if row.metric_name == "opportunity"
        ),
    )
    gap_table = _table(
        ("genre", "v1 rank", "v2 rank", "rank Δ", "v1", "v2", "value Δ"),
        (
            (
                row.display_name,
                row.v1_rank,
                row.v2_rank,
                row.rank_change,
                row.v1_value,
                row.v2_value,
                row.value_change,
            )
            for row in report.metric_changes
            if row.metric_name == "discovery_gap"
        ),
    )
    forecast_table = _table(
        (
            "genre",
            "axis",
            "h",
            "v1 status/model/MASE",
            "v2 status/model/MASE",
            "family MASE",
        ),
        (
            (
                row.genre_id,
                row.target_axis,
                row.horizon,
                f"{row.v1_status}/{row.v1_model}/{row.v1_mase}",
                f"{row.v2_status}/{row.v2_model}/{row.v2_mase}",
                row.v2_family_mase,
            )
            for row in report.forecast_skill_changes
        ),
    )
    missing_table = _table(
        ("genre", "v1 listen", "v2 listen", "v1 opp", "v2 opp", "changed"),
        (
            (
                row.display_name,
                row.v1_listening_missing,
                row.v2_listening_missing,
                row.v1_opportunity_missing,
                row.v2_opportunity_missing,
                row.changed,
            )
            for row in report.missingness_changes
        ),
    )
    checklist = _table(
        ("result", "scope", "gate", "observed", "threshold", "reason"),
        (
            (
                gate.passed,
                gate.scope,
                gate.gate_id,
                gate.observed,
                gate.threshold,
                gate.reason,
            )
            for gate in (
                *(
                    gate
                    for family in report.family_coverage
                    for gate in family.gates
                ),
                *report.global_gates,
            )
        ),
    )
    unresolved = report.unresolved
    quality = report.resolution_quality
    return "\n\n".join(
        (
            (
                "TAXONOMY VERSION COMPARISON\n"
                f"taxonomy={report.taxonomy_version} "
                f"coverage_week={report.latest_coverage_week} "
                f"common_metric_week={report.latest_common_metric_week}"
            ),
            f"GENRE COVERAGE\n{coverage_table}",
            f"FAMILY COVERAGE\n{family_table}",
            f"CHANGED MAPPINGS\n{mapping_table}",
            (
                "UNRESOLVED RATES\n"
                f"v1 other proxy: {unresolved.v1_other_tags}/"
                f"{unresolved.v1_mapped_tags} "
                f"({_display(unresolved.v1_other_rate)})\n"
                f"v2 explicit unresolved: {unresolved.v2_unresolved_tags}/"
                f"{unresolved.v2_mapped_tags} "
                f"({_display(unresolved.v2_unresolved_rate)})"
            ),
            (
                "RESOLUTION PRECISION / RECALL\n"
                f"v1 status={quality.v1_status} labels={quality.v1_labeled_examples} "
                f"precision={quality.v1_precision} recall={quality.v1_recall}\n"
                f"v2 status={quality.v2_status} labels={quality.v2_labeled_examples} "
                f"precision={quality.v2_precision} recall={quality.v2_recall}"
            ),
            f"OPPORTUNITY RANK CHANGES\n{opportunity_table}",
            f"DISCOVERY-GAP CHANGES\n{gap_table}",
            f"FORECAST SKILL CHANGES\n{forecast_table}",
            f"MISSINGNESS CHANGES\n{missing_table}",
            f"CUTOVER CHECKLIST\n{checklist}",
            (
                "CUTOVER DECISION\n"
                f"{'PASS' if report.cutover_passed else 'FAIL'} · "
                f"{report.failed_gate_count} failed gates · "
                f"action={report.cutover_action}"
            ),
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument(
        "--cutover-config",
        type=Path,
        default=DEFAULT_CUTOVER_CONFIG_PATH,
    )
    parser.add_argument(
        "--scaling-config",
        type=Path,
        default=DEFAULT_SCALING_CONFIG_PATH,
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-cutover",
        action="store_true",
        help="Exit nonzero when any cutover gate fails.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write the requested artifact without echoing the full report.",
    )
    return parser


def main() -> None:
    """CLI entry point."""

    args = _build_parser().parse_args()
    report = build_comparison_report(
        database_path=args.database,
        taxonomy_path=args.taxonomy,
        cutover_config_path=args.cutover_config,
        scaling_config_path=args.scaling_config,
    )
    rendered = (
        json.dumps(
            report.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
        if args.format == "json"
        else render_report(report)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    if not args.quiet:
        print(rendered)
    if args.require_cutover and not report.cutover_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
