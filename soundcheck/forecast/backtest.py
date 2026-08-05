"""Expanding-window rolling-origin backtests and model-score aggregation."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from soundcheck.forecast.estimators import (
    DEFAULT_GBM_ESTIMATORS,
    ets_forecast,
    lightgbm_forecasts,
    naive_forecast,
    seasonal_naive_forecast,
)
from soundcheck.forecast.features import ForecastDataset
from soundcheck.forecast.models import (
    BacktestRecord,
    ForecastEstimate,
    ForecastModelName,
    ModelScore,
    TargetAxis,
)

MIN_TRAINING_WEEKS = 8


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Rolling-origin controls kept injectable for focused synthetic tests."""

    minimum_training_weeks: int = MIN_TRAINING_WEEKS
    horizons: tuple[int, ...] = (1, 2)
    target_axes: tuple[TargetAxis, ...] = ("conversation", "listening")
    gbm_estimators: int = DEFAULT_GBM_ESTIMATORS


DEFAULT_BACKTEST_CONFIG = BacktestConfig()


def run_backtest(
    dataset: ForecastDataset,
    *,
    config: BacktestConfig = DEFAULT_BACKTEST_CONFIG,
    evaluated_at: datetime | None = None,
) -> tuple[tuple[BacktestRecord, ...], tuple[ModelScore, ...]]:
    """Run step-one-week expanding backtests without target-week leakage."""
    evaluation_time = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    records: list[BacktestRecord] = []
    available_weeks = set(dataset.weeks)
    for target_axis in config.target_axes:
        for horizon in config.horizons:
            for origin_week in dataset.weeks:
                target_week = origin_week + timedelta(weeks=horizon)
                if target_week not in available_weeks:
                    continue
                eligible = _eligible_genres(
                    dataset,
                    target_axis,
                    origin_week,
                    target_week,
                    config.minimum_training_weeks,
                )
                if not eligible:
                    continue
                gbm_examples = dataset.training_examples(
                    target_axis,
                    horizon,
                    target_cutoff_week=origin_week,
                )
                gbm_features = tuple(
                    features
                    for genre in eligible
                    if (
                        features := dataset.feature_vector(
                            genre,
                            target_axis,
                            horizon,
                            origin_week,
                        )
                    )
                    is not None
                )
                gbm_estimates = lightgbm_forecasts(
                    gbm_examples,
                    gbm_features,
                    estimators=config.gbm_estimators,
                )
                for genre in eligible:
                    history_weeks, history_values = dataset.contiguous_history(
                        genre,
                        target_axis,
                        origin_week,
                    )
                    actual = dataset.target_value(
                        genre,
                        target_week,
                        target_axis,
                    )
                    if actual is None:
                        continue
                    estimates: dict[ForecastModelName, ForecastEstimate | None] = {
                        "naive": naive_forecast(
                            dataset,
                            genre,
                            target_axis,
                            horizon,
                            origin_week,
                        ),
                        "seasonal_naive": seasonal_naive_forecast(
                            dataset,
                            genre,
                            target_axis,
                            horizon,
                            origin_week,
                        ),
                        "ets": ets_forecast(history_values, horizon),
                        "lightgbm": gbm_estimates.get(genre),
                    }
                    for model_name, estimate in estimates.items():
                        if estimate is None:
                            continue
                        records.append(
                            _backtest_record(
                                genre=genre,
                                target_axis=target_axis,
                                horizon=horizon,
                                model_name=model_name,
                                origin_week=origin_week,
                                target_week=target_week,
                                history_start=history_weeks[0],
                                training_weeks=len(history_weeks),
                                actual=actual,
                                estimate=estimate,
                            )
                        )
    ordered_records = tuple(
        sorted(
            records,
            key=lambda row: (
                row.target_axis,
                row.horizon,
                row.canonical_genre,
                row.model_name,
                row.origin_week,
            ),
        )
    )
    return ordered_records, score_backtests(
        ordered_records,
        evaluated_at=evaluation_time,
    )


def score_backtests(
    records: tuple[BacktestRecord, ...],
    *,
    evaluated_at: datetime,
) -> tuple[ModelScore, ...]:
    """Aggregate model MAE, relative MASE, and empirical 80% coverage."""
    grouped: dict[
        tuple[str, TargetAxis, int, ForecastModelName],
        list[BacktestRecord],
    ] = defaultdict(list)
    naive_by_origin = {
        (
            record.canonical_genre,
            record.target_axis,
            record.horizon,
            record.origin_week,
        ): record
        for record in records
        if record.model_name == "naive"
    }
    for record in records:
        grouped[
            (
                record.canonical_genre,
                record.target_axis,
                record.horizon,
                record.model_name,
            )
        ].append(record)

    scores: list[ModelScore] = []
    for (genre, axis, horizon, model_name), model_records in grouped.items():
        paired: list[tuple[BacktestRecord, BacktestRecord]] = []
        for record in model_records:
            naive = naive_by_origin.get(
                (genre, axis, horizon, record.origin_week)
            )
            if naive is not None:
                paired.append((record, naive))
        if not paired:
            continue
        model_errors = [record.absolute_error for record, _naive in paired]
        naive_errors = [naive.absolute_error for _record, naive in paired]
        mae = math.fsum(model_errors) / len(model_errors)
        naive_mae = math.fsum(naive_errors) / len(naive_errors)
        zero_scale = naive_mae <= 1e-12
        scores.append(
            ModelScore(
                canonical_genre=genre,
                target_axis=axis,
                horizon=horizon,
                model_name=model_name,
                backtest_start_week=min(
                    record.target_week for record, _naive in paired
                ),
                backtest_end_week=max(
                    record.target_week for record, _naive in paired
                ),
                origin_count=len(paired),
                mae=mae,
                naive_mae=naive_mae,
                mase=None if zero_scale else mae / naive_mae,
                interval_coverage_80=(
                    sum(record.covered_80 for record, _naive in paired)
                    / len(paired)
                ),
                mean_interval_width=(
                    math.fsum(
                        record.interval_high - record.interval_low
                        for record, _naive in paired
                    )
                    / len(paired)
                ),
                score_status="zero_naive_scale" if zero_scale else "scored",
                evaluated_at=evaluated_at,
            )
        )
    return tuple(
        sorted(
            scores,
            key=lambda score: (
                score.target_axis,
                score.horizon,
                score.canonical_genre,
                score.model_name,
            ),
        )
    )


def _eligible_genres(
    dataset: ForecastDataset,
    target_axis: TargetAxis,
    origin_week: date,
    target_week: date,
    minimum_training_weeks: int,
) -> tuple[str, ...]:
    eligible: list[str] = []
    for genre in dataset.genres:
        history_weeks, _history = dataset.contiguous_history(
            genre,
            target_axis,
            origin_week,
        )
        if (
            len(history_weeks) >= minimum_training_weeks
            and dataset.target_value(genre, target_week, target_axis) is not None
        ):
            eligible.append(genre)
    return tuple(eligible)


def _backtest_record(
    *,
    genre: str,
    target_axis: TargetAxis,
    horizon: int,
    model_name: ForecastModelName,
    origin_week: date,
    target_week: date,
    history_start: date,
    training_weeks: int,
    actual: float,
    estimate: ForecastEstimate,
) -> BacktestRecord:
    return BacktestRecord(
        canonical_genre=genre,
        target_axis=target_axis,
        horizon=horizon,
        model_name=model_name,
        origin_week=origin_week,
        target_week=target_week,
        training_start_week=history_start,
        training_end_week=origin_week,
        training_weeks=training_weeks,
        actual=actual,
        prediction=estimate.prediction,
        interval_low=estimate.interval_low,
        interval_high=estimate.interval_high,
        absolute_error=abs(actual - estimate.prediction),
        covered_80=estimate.interval_low <= actual <= estimate.interval_high,
    )
