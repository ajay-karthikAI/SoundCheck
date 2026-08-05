"""Family-validated rolling forecasts over taxonomy-v2 metric contexts."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import numpy as np

from soundcheck.forecast.estimators import (
    DEFAULT_GBM_ESTIMATORS,
    SEASONAL_PERIOD_WEEKS,
    ets_forecast,
    lightgbm_forecasts,
)
from soundcheck.forecast.models import (
    ForecastEstimate,
    ForecastModelName,
    TargetAxis,
    TrainingExample,
)
from soundcheck.forecast.v2_features import (
    CATEGORICAL_FEATURE_INDICES_V2,
    ForecastDatasetV2,
)
from soundcheck.forecast.v2_models import (
    BacktestRecordV2,
    ForecastBatchV2,
    ForecastHistoryRowV2,
    ForecastPredictionV2,
    ModelScoreV2,
    PopularityTier,
    ScoreStatusV2,
    ValidationScope,
)
from soundcheck.metrics.v2_models import MetricContext
from soundcheck.taxonomy import GenreDefinition, GenreTaxonomy

MINIMUM_TRAINING_WEEKS_V2 = 8
FORECAST_MODELS_V2: tuple[ForecastModelName, ...] = (
    "naive",
    "seasonal_naive",
    "ets",
    "lightgbm",
)
_CANDIDATE_MODELS: tuple[ForecastModelName, ...] = (
    "seasonal_naive",
    "ets",
    "lightgbm",
)


@dataclass(frozen=True, slots=True)
class BacktestConfigV2:
    """Injectable controls for expanding-window v2 validation."""

    minimum_training_weeks: int = MINIMUM_TRAINING_WEEKS_V2
    horizons: tuple[int, ...] = (1, 2)
    target_axes: tuple[TargetAxis, ...] = ("conversation", "listening")
    contexts: tuple[MetricContext, ...] = ("global", "peer_family")
    gbm_estimators: int = DEFAULT_GBM_ESTIMATORS


DEFAULT_BACKTEST_CONFIG_V2 = BacktestConfigV2()


def build_forecasts_v2(
    history_rows: tuple[ForecastHistoryRowV2, ...],
    taxonomy: GenreTaxonomy,
    *,
    created_at: datetime | None = None,
    config: BacktestConfigV2 = DEFAULT_BACKTEST_CONFIG_V2,
) -> ForecastBatchV2:
    """Backtest and publish v2 forecasts without mutating any v1 artifact."""
    if any(row.taxonomy_version != taxonomy.taxonomy_version for row in history_rows):
        raise ValueError("forecast history and taxonomy versions must match")
    forecast_time = (created_at or datetime.now(UTC)).astimezone(UTC)
    dataset = ForecastDatasetV2(history_rows)
    records = run_backtest_v2(dataset, config=config)
    scores = score_backtests_v2(
        records,
        dataset,
        taxonomy,
        config=config,
        evaluated_at=forecast_time,
    )
    predictions = _publish_predictions(
        dataset,
        taxonomy,
        scores,
        config=config,
        created_at=forecast_time,
    )
    return ForecastBatchV2(
        taxonomy_version=taxonomy.taxonomy_version,
        backtest_records=records,
        model_scores=scores,
        predictions=predictions,
        history_week_count=len(dataset.weeks),
    )


def run_backtest_v2(
    dataset: ForecastDatasetV2,
    *,
    config: BacktestConfigV2 = DEFAULT_BACKTEST_CONFIG_V2,
) -> tuple[BacktestRecordV2, ...]:
    """Run expanding origins; every feature and training target is as-of origin."""
    records: list[BacktestRecordV2] = []
    available_weeks = set(dataset.weeks)
    for context in config.contexts:
        for target_axis in config.target_axes:
            for horizon in config.horizons:
                for origin_week in dataset.weeks:
                    target_week = origin_week + timedelta(weeks=horizon)
                    if target_week not in available_weeks:
                        continue
                    eligible = _eligible_genres(
                        dataset,
                        context,
                        target_axis,
                        origin_week,
                        target_week,
                        config.minimum_training_weeks,
                    )
                    if not eligible:
                        continue
                    examples = _eligible_training_examples(
                        dataset,
                        context,
                        target_axis,
                        horizon,
                        origin_week,
                        config.minimum_training_weeks,
                    )
                    features = tuple(
                        feature
                        for genre_id in eligible
                        if (
                            feature := dataset.feature_vector(
                                genre_id,
                                context,
                                target_axis,
                                horizon,
                                origin_week,
                            )
                        )
                        is not None
                    )
                    gbm = lightgbm_forecasts(
                        examples,
                        features,
                        estimators=config.gbm_estimators,
                        categorical_feature_indices=(
                            CATEGORICAL_FEATURE_INDICES_V2
                        ),
                    )
                    for genre_id in eligible:
                        row = dataset.row(genre_id, context, origin_week)
                        if row is None:
                            continue
                        history_weeks, history_values = (
                            dataset.contiguous_history(
                                genre_id,
                                context,
                                target_axis,
                                origin_week,
                            )
                        )
                        actual = dataset.target_value(
                            genre_id,
                            context,
                            target_week,
                            target_axis,
                        )
                        if actual is None:
                            continue
                        estimates: dict[
                            ForecastModelName,
                            ForecastEstimate | None,
                        ] = {
                            "naive": _naive_forecast(
                                dataset,
                                genre_id,
                                context,
                                target_axis,
                                horizon,
                                origin_week,
                            ),
                            "seasonal_naive": _seasonal_naive_forecast(
                                dataset,
                                genre_id,
                                context,
                                target_axis,
                                horizon,
                                origin_week,
                            ),
                            "ets": ets_forecast(history_values, horizon),
                            "lightgbm": gbm.get(genre_id),
                        }
                        tier = dataset.popularity_tier(
                            genre_id,
                            context,
                            origin_week,
                        )
                        for model_name, estimate in estimates.items():
                            if estimate is None:
                                continue
                            records.append(
                                BacktestRecordV2(
                                    taxonomy_version=dataset.taxonomy_version,
                                    genre_id=genre_id,
                                    macro_family_id=row.macro_family_id,
                                    popularity_tier=tier,
                                    context=context,
                                    target_axis=target_axis,
                                    horizon=horizon,
                                    model_name=model_name,
                                    origin_week=origin_week,
                                    target_week=target_week,
                                    training_start_week=history_weeks[0],
                                    training_end_week=origin_week,
                                    training_weeks=len(history_weeks),
                                    max_feature_week=origin_week,
                                    actual=actual,
                                    prediction=estimate.prediction,
                                    interval_low=estimate.interval_low,
                                    interval_high=estimate.interval_high,
                                    absolute_error=abs(
                                        actual - estimate.prediction
                                    ),
                                    covered_80=(
                                        estimate.interval_low
                                        <= actual
                                        <= estimate.interval_high
                                    ),
                                )
                            )
    return tuple(
        sorted(
            records,
            key=lambda row: (
                row.context,
                row.target_axis,
                row.horizon,
                row.macro_family_id,
                row.popularity_tier,
                row.genre_id,
                row.model_name,
                row.origin_week,
            ),
        )
    )


def score_backtests_v2(
    records: tuple[BacktestRecordV2, ...],
    dataset: ForecastDatasetV2,
    taxonomy: GenreTaxonomy,
    *,
    config: BacktestConfigV2,
    evaluated_at: datetime,
) -> tuple[ModelScoreV2, ...]:
    """Score both genre-tier and family-tier groups against paired naive rows."""
    naive_by_origin = {
        _record_identity(record): record
        for record in records
        if record.model_name == "naive"
    }
    grouped: dict[
        tuple[
            ValidationScope,
            str,
            str | None,
            str,
            PopularityTier,
            MetricContext,
            TargetAxis,
            int,
            ForecastModelName,
        ],
        list[BacktestRecordV2],
    ] = defaultdict(list)
    for record in records:
        grouped[
            (
                "genre",
                f"{record.genre_id}:{record.popularity_tier}",
                record.genre_id,
                record.macro_family_id,
                record.popularity_tier,
                record.context,
                record.target_axis,
                record.horizon,
                record.model_name,
            )
        ].append(record)
        grouped[
            (
                "family_popularity",
                f"{record.macro_family_id}:{record.popularity_tier}",
                None,
                record.macro_family_id,
                record.popularity_tier,
                record.context,
                record.target_axis,
                record.horizon,
                record.model_name,
            )
        ].append(record)

    expected = _expected_score_keys(dataset, taxonomy, config)
    keys = tuple(sorted(set(grouped) | expected, key=_score_key_order))
    scores: list[ModelScoreV2] = []
    for key in keys:
        (
            scope,
            group_id,
            genre_id,
            family_id,
            tier,
            context,
            axis,
            horizon,
            model_name,
        ) = key
        paired = tuple(
            (record, naive)
            for record in grouped.get(key, ())
            if (
                naive := naive_by_origin.get(_record_identity(record))
            )
            is not None
        )
        if paired:
            scores.append(
                _scored_row(
                    scope=scope,
                    group_id=group_id,
                    genre_id=genre_id,
                    family_id=family_id,
                    tier=tier,
                    context=context,
                    axis=axis,
                    horizon=horizon,
                    model_name=model_name,
                    paired=paired,
                    evaluated_at=evaluated_at,
                    taxonomy_version=taxonomy.taxonomy_version,
                )
            )
            continue
        score_status = _unavailable_score_status(
            dataset,
            genre_id=genre_id,
            family_id=family_id,
            context=context,
            axis=axis,
            model_name=model_name,
            minimum_training_weeks=config.minimum_training_weeks,
        )
        scores.append(
            ModelScoreV2(
                taxonomy_version=taxonomy.taxonomy_version,
                validation_scope=scope,
                validation_group_id=group_id,
                genre_id=genre_id,
                macro_family_id=family_id,
                popularity_tier=tier,
                context=context,
                target_axis=axis,
                horizon=horizon,
                model_name=model_name,
                backtest_start_week=None,
                backtest_end_week=None,
                origin_count=0,
                mae=None,
                naive_mae=None,
                mase=None,
                interval_coverage_80=None,
                mean_interval_width=None,
                score_status=score_status,
                evaluated_at=evaluated_at,
            )
        )
    return tuple(scores)


def model_beats_relevant_naive(
    genre_score: ModelScoreV2 | None,
    family_score: ModelScoreV2 | None,
) -> bool:
    """Require skill in both the genre-tier and its family-tier validation group."""
    return bool(
        genre_score is not None
        and family_score is not None
        and genre_score.validation_scope == "genre"
        and family_score.validation_scope == "family_popularity"
        and genre_score.macro_family_id == family_score.macro_family_id
        and genre_score.popularity_tier == family_score.popularity_tier
        and genre_score.context == family_score.context
        and genre_score.target_axis == family_score.target_axis
        and genre_score.horizon == family_score.horizon
        and genre_score.model_name == family_score.model_name
        and genre_score.score_status == "scored"
        and family_score.score_status == "scored"
        and genre_score.mase is not None
        and family_score.mase is not None
        and genre_score.mase < 1.0
        and family_score.mase < 1.0
    )


def _publish_predictions(
    dataset: ForecastDatasetV2,
    taxonomy: GenreTaxonomy,
    scores: tuple[ModelScoreV2, ...],
    *,
    config: BacktestConfigV2,
    created_at: datetime,
) -> tuple[ForecastPredictionV2, ...]:
    latest_week = max(dataset.weeks, default=None)
    score_lookup = {
        (
            score.validation_scope,
            score.validation_group_id,
            score.context,
            score.target_axis,
            score.horizon,
            score.model_name,
        ): score
        for score in scores
    }
    predictions: list[ForecastPredictionV2] = []
    for context in config.contexts:
        for target_axis in config.target_axes:
            for horizon in config.horizons:
                gbm: dict[str, ForecastEstimate] = {}
                if latest_week is not None:
                    eligible = tuple(
                        genre.genre_id
                        for genre in taxonomy.genres
                        if len(
                            dataset.contiguous_history(
                                genre.genre_id,
                                context,
                                target_axis,
                                latest_week,
                            )[0]
                        )
                        >= config.minimum_training_weeks
                    )
                    examples = _eligible_training_examples(
                        dataset,
                        context,
                        target_axis,
                        horizon,
                        latest_week,
                        config.minimum_training_weeks,
                    )
                    features = tuple(
                        feature
                        for genre_id in eligible
                        if (
                            feature := dataset.feature_vector(
                                genre_id,
                                context,
                                target_axis,
                                horizon,
                                latest_week,
                            )
                        )
                        is not None
                    )
                    gbm = lightgbm_forecasts(
                        examples,
                        features,
                        estimators=config.gbm_estimators,
                        categorical_feature_indices=(
                            CATEGORICAL_FEATURE_INDICES_V2
                        ),
                    )
                for genre in taxonomy.genres:
                    predictions.append(
                        _prediction_for_genre(
                            dataset,
                            genre,
                            context,
                            target_axis,
                            horizon,
                            latest_week,
                            gbm,
                            score_lookup,
                            config=config,
                            created_at=created_at,
                            taxonomy_version=taxonomy.taxonomy_version,
                        )
                    )
    return tuple(
        sorted(
            predictions,
            key=lambda row: (
                row.context,
                row.target_axis,
                row.horizon,
                row.macro_family_id,
                row.genre_id,
            ),
        )
    )


def _prediction_for_genre(
    dataset: ForecastDatasetV2,
    genre: GenreDefinition,
    context: MetricContext,
    target_axis: TargetAxis,
    horizon: int,
    latest_week: date | None,
    gbm: dict[str, ForecastEstimate],
    score_lookup: dict[
        tuple[
            ValidationScope,
            str,
            MetricContext,
            TargetAxis,
            int,
            ForecastModelName,
        ],
        ModelScoreV2,
    ],
    *,
    config: BacktestConfigV2,
    created_at: datetime,
    taxonomy_version: str,
) -> ForecastPredictionV2:
    if latest_week is None:
        return _empty_prediction(
            genre,
            context,
            target_axis,
            horizon,
            latest_week=None,
            tier="unknown",
            valid_training_weeks=0,
            status="insufficient_history",
            taxonomy_version=taxonomy_version,
            created_at=created_at,
        )
    current = dataset.row(genre.genre_id, context, latest_week)
    tier = dataset.popularity_tier(genre.genre_id, context, latest_week)
    history_weeks, history_values = dataset.contiguous_history(
        genre.genre_id,
        context,
        target_axis,
        latest_week,
    )
    if (
        genre.status == "rejected"
        or current is None
        or current.coverage_state == "unsupported"
    ):
        return _empty_prediction(
            genre,
            context,
            target_axis,
            horizon,
            latest_week=latest_week,
            tier=tier,
            valid_training_weeks=len(history_weeks),
            status="insufficient_evidence",
            taxonomy_version=taxonomy_version,
            created_at=created_at,
        )
    if len(history_weeks) < config.minimum_training_weeks:
        return _empty_prediction(
            genre,
            context,
            target_axis,
            horizon,
            latest_week=latest_week,
            tier=tier,
            valid_training_weeks=len(history_weeks),
            status="insufficient_history",
            taxonomy_version=taxonomy_version,
            created_at=created_at,
        )

    genre_group = f"{genre.genre_id}:{tier}"
    family_group = f"{genre.macro_family_id}:{tier}"
    naive_score = score_lookup.get(
        ("genre", genre_group, context, target_axis, horizon, "naive")
    )
    family_naive = score_lookup.get(
        (
            "family_popularity",
            family_group,
            context,
            target_axis,
            horizon,
            "naive",
        )
    )
    naive_estimate = _naive_forecast(
        dataset,
        genre.genre_id,
        context,
        target_axis,
        horizon,
        latest_week,
    )
    if (
        naive_score is None
        or family_naive is None
        or naive_score.origin_count == 0
        or family_naive.origin_count == 0
        or naive_estimate is None
        or naive_score.interval_coverage_80 is None
    ):
        return _empty_prediction(
            genre,
            context,
            target_axis,
            horizon,
            latest_week=latest_week,
            tier=tier,
            valid_training_weeks=len(history_weeks),
            status="insufficient_history",
            taxonomy_version=taxonomy_version,
            created_at=created_at,
        )

    estimates: dict[ForecastModelName, ForecastEstimate | None] = {
        "seasonal_naive": _seasonal_naive_forecast(
            dataset,
            genre.genre_id,
            context,
            target_axis,
            horizon,
            latest_week,
        ),
        "ets": ets_forecast(history_values, horizon),
        "lightgbm": gbm.get(genre.genre_id),
    }
    candidates: list[tuple[ModelScoreV2, ModelScoreV2, ForecastEstimate]] = []
    for model_name in _CANDIDATE_MODELS:
        genre_score = score_lookup.get(
            ("genre", genre_group, context, target_axis, horizon, model_name)
        )
        family_score = score_lookup.get(
            (
                "family_popularity",
                family_group,
                context,
                target_axis,
                horizon,
                model_name,
            )
        )
        estimate = estimates[model_name]
        if (
            estimate is not None
            and model_beats_relevant_naive(genre_score, family_score)
            and genre_score is not None
            and family_score is not None
        ):
            candidates.append((genre_score, family_score, estimate))
    selected = (
        min(
            candidates,
            key=lambda item: (
                item[0].mase
                if item[0].mase is not None
                else float("inf")
            ),
        )
        if candidates
        else None
    )
    selected_score = naive_score if selected is None else selected[0]
    selected_family = family_naive if selected is None else selected[1]
    selected_estimate = naive_estimate if selected is None else selected[2]
    return ForecastPredictionV2(
        taxonomy_version=taxonomy_version,
        origin_week=latest_week,
        target_week=latest_week + timedelta(weeks=horizon),
        genre_id=genre.genre_id,
        display_name=genre.display_name,
        macro_family_id=genre.macro_family_id,
        popularity_tier=tier,
        context=context,
        target_axis=target_axis,
        horizon=horizon,
        forecast_status="no_skill" if selected is None else "ready",
        model_name=selected_score.model_name,
        prediction=selected_estimate.prediction,
        interval_low=selected_estimate.interval_low,
        interval_high=selected_estimate.interval_high,
        backtest_mase=selected_score.mase,
        backtest_coverage_80=selected_score.interval_coverage_80,
        backtest_score_status=selected_score.score_status,
        family_backtest_mase=selected_family.mase,
        family_backtest_coverage_80=(
            selected_family.interval_coverage_80
        ),
        family_backtest_score_status=selected_family.score_status,
        naive_prediction=naive_estimate.prediction,
        naive_interval_low=naive_estimate.interval_low,
        naive_interval_high=naive_estimate.interval_high,
        naive_backtest_mase=naive_score.mase,
        naive_backtest_coverage_80=naive_score.interval_coverage_80,
        naive_backtest_score_status=naive_score.score_status,
        valid_training_weeks=len(history_weeks),
        training_start_week=history_weeks[0],
        training_end_week=latest_week,
        created_at=created_at,
    )


def _empty_prediction(
    genre: GenreDefinition,
    context: MetricContext,
    target_axis: TargetAxis,
    horizon: int,
    *,
    latest_week: date | None,
    tier: PopularityTier,
    valid_training_weeks: int,
    status: Literal["insufficient_history", "insufficient_evidence"],
    taxonomy_version: str,
    created_at: datetime,
) -> ForecastPredictionV2:
    return ForecastPredictionV2(
        taxonomy_version=taxonomy_version,
        origin_week=latest_week,
        target_week=(
            None
            if latest_week is None
            else latest_week + timedelta(weeks=horizon)
        ),
        genre_id=genre.genre_id,
        display_name=genre.display_name,
        macro_family_id=genre.macro_family_id,
        popularity_tier=tier,
        context=context,
        target_axis=target_axis,
        horizon=horizon,
        forecast_status=status,
        model_name=None,
        prediction=None,
        interval_low=None,
        interval_high=None,
        backtest_mase=None,
        backtest_coverage_80=None,
        backtest_score_status=None,
        family_backtest_mase=None,
        family_backtest_coverage_80=None,
        family_backtest_score_status=None,
        naive_prediction=None,
        naive_interval_low=None,
        naive_interval_high=None,
        naive_backtest_mase=None,
        naive_backtest_coverage_80=None,
        naive_backtest_score_status=None,
        valid_training_weeks=valid_training_weeks,
        training_start_week=None,
        training_end_week=None,
        created_at=created_at,
    )


def _eligible_training_examples(
    dataset: ForecastDatasetV2,
    context: MetricContext,
    axis: TargetAxis,
    horizon: int,
    cutoff: date,
    minimum_weeks: int,
) -> tuple[TrainingExample, ...]:
    examples = dataset.training_examples(
        context,
        axis,
        horizon,
        target_cutoff_week=cutoff,
    )
    return tuple(
        example
        for example in examples
        if len(
            dataset.contiguous_history(
                example.features.canonical_genre,
                context,
                axis,
                example.features.origin_week,
            )[0]
        )
        >= minimum_weeks
    )


def _eligible_genres(
    dataset: ForecastDatasetV2,
    context: MetricContext,
    axis: TargetAxis,
    origin_week: date,
    target_week: date,
    minimum_weeks: int,
) -> tuple[str, ...]:
    return tuple(
        genre_id
        for genre_id in dataset.genres
        if len(
            dataset.contiguous_history(
                genre_id,
                context,
                axis,
                origin_week,
            )[0]
        )
        >= minimum_weeks
        and dataset.target_value(
            genre_id,
            context,
            target_week,
            axis,
        )
        is not None
    )


def _naive_forecast(
    dataset: ForecastDatasetV2,
    genre_id: str,
    context: MetricContext,
    axis: TargetAxis,
    horizon: int,
    origin_week: date,
) -> ForecastEstimate | None:
    point = dataset.target_value(genre_id, context, origin_week, axis)
    if point is None:
        return None
    errors = dataset.historical_persistence_errors(
        genre_id,
        context,
        axis,
        horizon,
        origin_week,
    )
    return _residual_interval(point, errors)


def _seasonal_naive_forecast(
    dataset: ForecastDatasetV2,
    genre_id: str,
    context: MetricContext,
    axis: TargetAxis,
    horizon: int,
    origin_week: date,
) -> ForecastEstimate | None:
    target_week = origin_week + timedelta(weeks=horizon)
    point = dataset.target_value(
        genre_id,
        context,
        target_week - timedelta(weeks=SEASONAL_PERIOD_WEEKS),
        axis,
    )
    if point is None:
        return None
    errors = dataset.historical_seasonal_errors(
        genre_id,
        context,
        axis,
        origin_week,
        period_weeks=SEASONAL_PERIOD_WEEKS,
    )
    return _residual_interval(point, errors)


def _residual_interval(
    point: float,
    residuals: tuple[float, ...],
) -> ForecastEstimate:
    finite = np.asarray(
        [value for value in residuals if math.isfinite(value)],
        dtype=np.float64,
    )
    if len(finite) == 0:
        return ForecastEstimate(
            prediction=point,
            interval_low=point,
            interval_high=point,
        )
    low, high = np.quantile(finite, [0.10, 0.90])
    return ForecastEstimate(
        prediction=point,
        interval_low=min(point, point + float(low)),
        interval_high=max(point, point + float(high)),
    )


def _record_identity(
    record: BacktestRecordV2,
) -> tuple[str, MetricContext, TargetAxis, int, str, date]:
    return (
        record.taxonomy_version,
        record.context,
        record.target_axis,
        record.horizon,
        record.genre_id,
        record.origin_week,
    )


def _scored_row(
    *,
    scope: ValidationScope,
    group_id: str,
    genre_id: str | None,
    family_id: str,
    tier: PopularityTier,
    context: MetricContext,
    axis: TargetAxis,
    horizon: int,
    model_name: ForecastModelName,
    paired: tuple[tuple[BacktestRecordV2, BacktestRecordV2], ...],
    evaluated_at: datetime,
    taxonomy_version: str,
) -> ModelScoreV2:
    errors = tuple(record.absolute_error for record, _naive in paired)
    naive_errors = tuple(naive.absolute_error for _record, naive in paired)
    mae = math.fsum(errors) / len(errors)
    naive_mae = math.fsum(naive_errors) / len(naive_errors)
    zero_scale = naive_mae <= 1e-12
    return ModelScoreV2(
        taxonomy_version=taxonomy_version,
        validation_scope=scope,
        validation_group_id=group_id,
        genre_id=genre_id,
        macro_family_id=family_id,
        popularity_tier=tier,
        context=context,
        target_axis=axis,
        horizon=horizon,
        model_name=model_name,
        backtest_start_week=min(record.target_week for record, _ in paired),
        backtest_end_week=max(record.target_week for record, _ in paired),
        origin_count=len(paired),
        mae=mae,
        naive_mae=naive_mae,
        mase=None if zero_scale else mae / naive_mae,
        interval_coverage_80=(
            sum(record.covered_80 for record, _naive in paired) / len(paired)
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


def _expected_score_keys(
    dataset: ForecastDatasetV2,
    taxonomy: GenreTaxonomy,
    config: BacktestConfigV2,
) -> set[
    tuple[
        ValidationScope,
        str,
        str | None,
        str,
        PopularityTier,
        MetricContext,
        TargetAxis,
        int,
        ForecastModelName,
    ]
]:
    latest = max(dataset.weeks, default=None)
    keys: set[
        tuple[
            ValidationScope,
            str,
            str | None,
            str,
            PopularityTier,
            MetricContext,
            TargetAxis,
            int,
            ForecastModelName,
        ]
    ] = set()
    for context in config.contexts:
        family_tiers: set[tuple[str, PopularityTier]] = set()
        for genre in taxonomy.genres:
            tier: PopularityTier = (
                "unknown" if latest is None else dataset.popularity_tier(
                    genre.genre_id,
                    context,
                    latest,
                )
            )
            family_tiers.add((genre.macro_family_id, tier))
            for axis in config.target_axes:
                for horizon in config.horizons:
                    for model_name in FORECAST_MODELS_V2:
                        keys.add(
                            (
                                "genre",
                                f"{genre.genre_id}:{tier}",
                                genre.genre_id,
                                genre.macro_family_id,
                                tier,
                                context,
                                axis,
                                horizon,
                                model_name,
                            )
                        )
        for family_id, tier in family_tiers:
            for axis in config.target_axes:
                for horizon in config.horizons:
                    for model_name in FORECAST_MODELS_V2:
                        keys.add(
                            (
                                "family_popularity",
                                f"{family_id}:{tier}",
                                None,
                                family_id,
                                tier,
                                context,
                                axis,
                                horizon,
                                model_name,
                            )
                        )
    return keys


def _unavailable_score_status(
    dataset: ForecastDatasetV2,
    *,
    genre_id: str | None,
    family_id: str,
    context: MetricContext,
    axis: TargetAxis,
    model_name: ForecastModelName,
    minimum_training_weeks: int,
) -> ScoreStatusV2:
    latest = max(dataset.weeks, default=None)
    if latest is None:
        return "insufficient_history"
    candidates = (
        (genre_id,)
        if genre_id is not None
        else tuple(
            candidate
            for candidate in dataset.genres
            if (
                (row := dataset.row(candidate, context, latest)) is not None
                and row.macro_family_id == family_id
            )
        )
    )
    maximum = max(
        (
            len(
                dataset.contiguous_history(
                    candidate,
                    context,
                    axis,
                    latest,
                )[0]
            )
            for candidate in candidates
        ),
        default=0,
    )
    if maximum < minimum_training_weeks or model_name == "naive":
        return "insufficient_history"
    return "unavailable_model"


def _score_key_order(
    key: tuple[
        ValidationScope,
        str,
        str | None,
        str,
        PopularityTier,
        MetricContext,
        TargetAxis,
        int,
        ForecastModelName,
    ],
) -> tuple[object, ...]:
    return (
        key[5],
        key[6],
        key[7],
        key[0],
        key[3],
        key[4],
        key[2] or "",
        key[8],
    )
