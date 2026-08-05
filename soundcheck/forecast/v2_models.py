"""Validated taxonomy-v2 forecast, backtest, and publication contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from soundcheck.forecast.models import ForecastModelName, TargetAxis
from soundcheck.metrics.v2_models import MetricContext
from soundcheck.taxonomy import GenreStatus

PopularityTier = Literal["low", "middle", "high", "unknown"]
ValidationScope = Literal["genre", "family_popularity"]
ScoreStatusV2 = Literal[
    "scored",
    "zero_naive_scale",
    "insufficient_history",
    "unavailable_model",
]
ForecastStatusV2 = Literal[
    "ready",
    "no_skill",
    "insufficient_history",
    "insufficient_evidence",
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class ForecastHistoryRowV2(BaseModel):
    """One genre/context/week row loaded from taxonomy-v2 metric artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    genre_id: str
    display_name: str
    macro_family_id: str
    parent_genre_id: str | None
    taxonomy_status: GenreStatus
    coverage_state: str
    estimate_eligible: bool
    context: MetricContext
    conversation: float | None
    listening: float | None
    supply: float | None
    discovery_gap: float | None
    opportunity: float | None
    conversation_ewma: float | None
    listening_ewma: float | None
    supply_ewma: float | None
    conversation_spike: bool | None
    listening_spike: bool | None
    supply_spike: bool | None
    conversation_effective_n: float | None = Field(default=None, ge=0.0)
    listening_effective_n: float | None = Field(default=None, ge=0.0)


class BacktestRecordV2(BaseModel):
    """One leakage-safe held-out forecast with family and tier provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    genre_id: str
    macro_family_id: str
    popularity_tier: PopularityTier
    context: MetricContext
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    model_name: ForecastModelName
    origin_week: date
    target_week: date
    training_start_week: date
    training_end_week: date
    training_weeks: int = Field(ge=8)
    max_feature_week: date
    actual: float
    prediction: float
    interval_low: float
    interval_high: float
    absolute_error: float = Field(ge=0.0)
    covered_80: bool

    @model_validator(mode="after")
    def validate_no_leakage_and_interval(self) -> BacktestRecordV2:
        if self.max_feature_week > self.origin_week:
            raise ValueError("backtest features contain post-origin information")
        if self.training_end_week > self.origin_week:
            raise ValueError("training data extends beyond the origin")
        if self.origin_week >= self.target_week:
            raise ValueError("target week must be after the origin")
        if not self.interval_low <= self.prediction <= self.interval_high:
            raise ValueError("prediction interval must contain its point")
        return self


class ModelScoreV2(BaseModel):
    """A complete genre or family-tier validation ledger row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    validation_scope: ValidationScope
    validation_group_id: str
    genre_id: str | None
    macro_family_id: str
    popularity_tier: PopularityTier
    context: MetricContext
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    model_name: ForecastModelName
    backtest_start_week: date | None
    backtest_end_week: date | None
    origin_count: int = Field(ge=0)
    mae: float | None = Field(default=None, ge=0.0)
    naive_mae: float | None = Field(default=None, ge=0.0)
    mase: float | None = Field(default=None, ge=0.0)
    interval_coverage_80: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_interval_width: float | None = Field(default=None, ge=0.0)
    score_status: ScoreStatusV2
    evaluated_at: datetime

    _evaluated_at_utc = field_validator("evaluated_at")(_as_utc)

    @model_validator(mode="after")
    def validate_score_state(self) -> ModelScoreV2:
        metrics = (
            self.mae,
            self.naive_mae,
            self.interval_coverage_80,
            self.mean_interval_width,
        )
        if self.score_status in {"scored", "zero_naive_scale"}:
            if self.origin_count == 0 or any(value is None for value in metrics):
                raise ValueError("scored ledgers require held-out metrics")
            if self.backtest_start_week is None or self.backtest_end_week is None:
                raise ValueError("scored ledgers require a backtest date range")
        else:
            if self.origin_count != 0 or any(value is not None for value in metrics):
                raise ValueError("unscored ledgers must keep validation metrics null")
            if self.mase is not None:
                raise ValueError("unscored ledgers cannot claim MASE")
        if self.score_status == "zero_naive_scale" and self.mase is not None:
            raise ValueError("MASE is undefined with a zero naive scale")
        return self


class ForecastPredictionV2(BaseModel):
    """One genre/context/axis/horizon publication row, including cold starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    origin_week: date | None
    target_week: date | None
    genre_id: str
    display_name: str
    macro_family_id: str
    popularity_tier: PopularityTier
    context: MetricContext
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    forecast_status: ForecastStatusV2
    model_name: ForecastModelName | None
    prediction: float | None
    interval_low: float | None
    interval_high: float | None
    backtest_mase: float | None = Field(default=None, ge=0.0)
    backtest_coverage_80: float | None = Field(default=None, ge=0.0, le=1.0)
    backtest_score_status: ScoreStatusV2 | None
    family_backtest_mase: float | None = Field(default=None, ge=0.0)
    family_backtest_coverage_80: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    family_backtest_score_status: ScoreStatusV2 | None
    naive_prediction: float | None
    naive_interval_low: float | None
    naive_interval_high: float | None
    naive_backtest_mase: float | None = Field(default=None, ge=0.0)
    naive_backtest_coverage_80: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    naive_backtest_score_status: ScoreStatusV2 | None
    valid_training_weeks: int = Field(ge=0)
    training_start_week: date | None
    training_end_week: date | None
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)

    @model_validator(mode="after")
    def validate_publication_state(self) -> ForecastPredictionV2:
        selected = (
            self.prediction,
            self.interval_low,
            self.interval_high,
            self.backtest_coverage_80,
            self.family_backtest_coverage_80,
        )
        baseline = (
            self.naive_prediction,
            self.naive_interval_low,
            self.naive_interval_high,
            self.naive_backtest_coverage_80,
        )
        if self.forecast_status in {"ready", "no_skill"}:
            if self.model_name is None or any(value is None for value in selected):
                raise ValueError("publishable forecasts require estimates and coverage")
            if any(value is None for value in baseline):
                raise ValueError("publishable forecasts require the naive baseline")
            if (
                self.backtest_score_status is None
                or self.family_backtest_score_status is None
                or self.naive_backtest_score_status is None
            ):
                raise ValueError("publishable forecasts require score statuses")
            if self.forecast_status == "ready" and self.model_name == "naive":
                raise ValueError("a ready skill claim cannot select naive")
            if self.forecast_status == "no_skill" and self.model_name != "naive":
                raise ValueError("no_skill must publish the naive forecast")
            if (
                self.interval_low is None
                or self.prediction is None
                or self.interval_high is None
                or not self.interval_low <= self.prediction <= self.interval_high
            ):
                raise ValueError("selected interval must contain its point")
            if (
                self.naive_interval_low is None
                or self.naive_prediction is None
                or self.naive_interval_high is None
                or not self.naive_interval_low
                <= self.naive_prediction
                <= self.naive_interval_high
            ):
                raise ValueError("naive interval must contain its point")
        else:
            unavailable_fields = (
                self.model_name,
                *selected,
                self.backtest_mase,
                self.backtest_score_status,
                self.family_backtest_mase,
                self.family_backtest_score_status,
                *baseline,
                self.naive_backtest_mase,
                self.naive_backtest_score_status,
            )
            if any(value is not None for value in unavailable_fields):
                raise ValueError("unavailable forecasts cannot carry a skill claim")
        return self


class ForecastBatchV2(BaseModel):
    """Version-isolated v2 forecast artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    backtest_records: tuple[BacktestRecordV2, ...]
    model_scores: tuple[ModelScoreV2, ...]
    predictions: tuple[ForecastPredictionV2, ...]
    history_week_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_version_isolation(self) -> ForecastBatchV2:
        versions = (
            *(row.taxonomy_version for row in self.backtest_records),
            *(row.taxonomy_version for row in self.model_scores),
            *(row.taxonomy_version for row in self.predictions),
        )
        if any(version != self.taxonomy_version for version in versions):
            raise ValueError("v2 forecast artifacts cannot mix taxonomy versions")
        return self
