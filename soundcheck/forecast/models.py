"""Validated forecast history, backtest, score, and publication models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type TargetAxis = Literal["conversation", "listening"]
type ForecastModelName = Literal[
    "naive",
    "seasonal_naive",
    "ets",
    "lightgbm",
]
type SkillStatus = Literal["baseline", "skill", "no_skill"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class ForecastHistoryRow(BaseModel):
    """One canonical-genre/week feature row loaded from the metrics mart."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    canonical_genre: str
    conversation_index: float
    listening_index: float | None
    supply_index: float
    supply_index_ci_low: float
    supply_index_ci_high: float
    discovery_gap: float | None
    conversation_ewma: float
    listening_ewma: float | None
    supply_ewma: float
    conversation_spike: bool
    listening_spike: bool
    supply_spike: bool
    opportunity: float | None
    opportunity_ci_low: float | None
    opportunity_ci_high: float | None
    breakout_precursor: bool
    genre_embedding: tuple[float, ...]


class FeatureVector(BaseModel):
    """Leakage-auditable global-model feature vector."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    origin_week: date
    target_week: date
    max_observed_week: date
    feature_names: tuple[str, ...]
    values: tuple[float, ...]

    @model_validator(mode="after")
    def validate_shape_and_leakage(self) -> FeatureVector:
        if len(self.feature_names) != len(self.values):
            msg = "feature names and values must have equal length"
            raise ValueError(msg)
        if self.max_observed_week > self.origin_week:
            msg = "feature vector contains post-origin information"
            raise ValueError(msg)
        return self


class TrainingExample(BaseModel):
    """One global-model example whose target is known by its training origin."""

    model_config = ConfigDict(frozen=True)

    features: FeatureVector
    target_value: float


class ForecastEstimate(BaseModel):
    """One point forecast with an 80% prediction interval."""

    model_config = ConfigDict(frozen=True)

    prediction: float
    interval_low: float
    interval_high: float

    @model_validator(mode="after")
    def validate_interval(self) -> ForecastEstimate:
        if not self.interval_low <= self.prediction <= self.interval_high:
            msg = "prediction interval must contain its point forecast"
            raise ValueError(msg)
        return self


class BacktestRecord(BaseModel):
    """One leakage-safe rolling-origin forecast outcome."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    model_name: ForecastModelName
    origin_week: date
    target_week: date
    training_start_week: date
    training_end_week: date
    training_weeks: int = Field(ge=8)
    actual: float
    prediction: float
    interval_low: float
    interval_high: float
    absolute_error: float = Field(ge=0)
    covered_80: bool


class ModelScore(BaseModel):
    """Aggregate rolling-origin skill and calibration for one model."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    model_name: ForecastModelName
    backtest_start_week: date
    backtest_end_week: date
    origin_count: int = Field(gt=0)
    mae: float = Field(ge=0)
    naive_mae: float = Field(ge=0)
    mase: float | None = Field(default=None, ge=0)
    interval_coverage_80: float = Field(ge=0, le=1)
    mean_interval_width: float = Field(ge=0)
    score_status: Literal["scored", "zero_naive_scale"]
    evaluated_at: datetime

    _evaluated_at_utc = field_validator("evaluated_at")(_as_utc)


class ForecastPrediction(BaseModel):
    """One publishable future forecast backed by a model score."""

    model_config = ConfigDict(frozen=True)

    origin_week: date
    target_week: date
    canonical_genre: str
    target_axis: TargetAxis
    horizon: int = Field(ge=1, le=2)
    model_name: ForecastModelName
    is_naive_baseline: bool
    skill_status: SkillStatus
    prediction: float
    interval_low: float
    interval_high: float
    backtest_mase: float | None = Field(default=None, ge=0)
    backtest_coverage_80: float = Field(ge=0, le=1)
    backtest_origin_count: int = Field(gt=0)
    training_start_week: date
    training_end_week: date
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)

    @model_validator(mode="after")
    def validate_prediction(self) -> ForecastPrediction:
        if not self.interval_low <= self.prediction <= self.interval_high:
            msg = "prediction interval must contain its point forecast"
            raise ValueError(msg)
        return self


class NextUpPrediction(BaseModel):
    """Breakout-filtered predicted opportunity gain for the marquee ranking."""

    model_config = ConfigDict(frozen=True)

    origin_week: date
    target_week: date
    canonical_genre: str
    rank: int = Field(gt=0)
    predicted_opportunity: float
    predicted_opportunity_interval_low: float
    predicted_opportunity_interval_high: float
    predicted_gain: float
    gain_interval_low: float
    gain_interval_high: float
    conversation_model: ForecastModelName
    listening_model: ForecastModelName
    conversation_mase: float | None = Field(default=None, ge=0)
    listening_mase: float | None = Field(default=None, ge=0)
    skill_status: Literal["skill", "no_skill"]
    breakout_evidence_week: date
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)

    @model_validator(mode="after")
    def validate_gain_interval(self) -> NextUpPrediction:
        if not (
            self.predicted_opportunity_interval_low
            <= self.predicted_opportunity
            <= self.predicted_opportunity_interval_high
        ):
            msg = "opportunity interval must contain its point forecast"
            raise ValueError(msg)
        if not self.gain_interval_low <= self.predicted_gain <= self.gain_interval_high:
            msg = "gain interval must contain its point forecast"
            raise ValueError(msg)
        return self


class ForecastBatch(BaseModel):
    """Atomic forecast, backtest, model-score, and next-up replacement."""

    model_config = ConfigDict(frozen=True)

    backtest_records: tuple[BacktestRecord, ...]
    model_scores: tuple[ModelScore, ...]
    predictions: tuple[ForecastPrediction, ...]
    next_up: tuple[NextUpPrediction, ...]
    history_week_count: int = Field(ge=0)
