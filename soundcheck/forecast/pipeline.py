"""Backtest-gated forecast publication and next-up ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from soundcheck.forecast.backtest import (
    DEFAULT_BACKTEST_CONFIG,
    BacktestConfig,
    run_backtest,
)
from soundcheck.forecast.estimators import (
    ets_forecast,
    lightgbm_forecasts,
    naive_forecast,
    seasonal_naive_forecast,
)
from soundcheck.forecast.features import ForecastDataset
from soundcheck.forecast.models import (
    ForecastBatch,
    ForecastEstimate,
    ForecastHistoryRow,
    ForecastModelName,
    ForecastPrediction,
    ModelScore,
    NextUpPrediction,
    SkillStatus,
    TargetAxis,
)

_CANDIDATE_MODEL_NAMES: tuple[ForecastModelName, ...] = (
    "seasonal_naive",
    "ets",
    "lightgbm",
)


@dataclass(frozen=True)
class _NextUpCandidate:
    canonical_genre: str
    predicted_opportunity: float
    predicted_opportunity_interval_low: float
    predicted_opportunity_interval_high: float
    predicted_gain: float
    gain_interval_low: float
    gain_interval_high: float
    conversation: ForecastPrediction
    listening: ForecastPrediction


def build_forecasts(
    history_rows: tuple[ForecastHistoryRow, ...],
    *,
    created_at: datetime | None = None,
    backtest_config: BacktestConfig = DEFAULT_BACKTEST_CONFIG,
) -> ForecastBatch:
    """Backtest every model, publish only scored forecasts, and rank quiet risers."""
    forecast_time = (created_at or datetime.now(UTC)).astimezone(UTC)
    dataset = ForecastDataset(history_rows)
    backtest_records, model_scores = run_backtest(
        dataset,
        config=backtest_config,
        evaluated_at=forecast_time,
    )
    if not dataset.weeks:
        return ForecastBatch(
            backtest_records=backtest_records,
            model_scores=model_scores,
            predictions=(),
            next_up=(),
            history_week_count=0,
        )

    latest_week = max(dataset.weeks)
    score_lookup = {
        (
            score.canonical_genre,
            score.target_axis,
            score.horizon,
            score.model_name,
        ): score
        for score in model_scores
    }
    predictions: list[ForecastPrediction] = []
    for target_axis in backtest_config.target_axes:
        for horizon in backtest_config.horizons:
            eligible = tuple(
                genre
                for genre in dataset.genres
                if len(
                    dataset.contiguous_history(
                        genre,
                        target_axis,
                        latest_week,
                    )[0]
                )
                >= backtest_config.minimum_training_weeks
            )
            gbm_examples = dataset.training_examples(
                target_axis,
                horizon,
                target_cutoff_week=latest_week,
            )
            gbm_features = tuple(
                features
                for genre in eligible
                if (
                    features := dataset.feature_vector(
                        genre,
                        target_axis,
                        horizon,
                        latest_week,
                    )
                )
                is not None
            )
            gbm_estimates = lightgbm_forecasts(
                gbm_examples,
                gbm_features,
                estimators=backtest_config.gbm_estimators,
            )
            for genre in eligible:
                history_weeks, history_values = dataset.contiguous_history(
                    genre,
                    target_axis,
                    latest_week,
                )
                naive_score = score_lookup.get(
                    (genre, target_axis, horizon, "naive")
                )
                naive_estimate = naive_forecast(
                    dataset,
                    genre,
                    target_axis,
                    horizon,
                    latest_week,
                )
                if naive_score is None or naive_estimate is None:
                    continue
                estimates: dict[ForecastModelName, ForecastEstimate | None] = {
                    "seasonal_naive": seasonal_naive_forecast(
                        dataset,
                        genre,
                        target_axis,
                        horizon,
                        latest_week,
                    ),
                    "ets": ets_forecast(history_values, horizon),
                    "lightgbm": gbm_estimates.get(genre),
                }
                skilled_candidates: list[
                    tuple[ModelScore, ForecastEstimate]
                ] = []
                for model_name in _CANDIDATE_MODEL_NAMES:
                    score = score_lookup.get(
                        (genre, target_axis, horizon, model_name)
                    )
                    estimate = estimates[model_name]
                    if (
                        score is not None
                        and score.mase is not None
                        and score.mase < 1.0
                        and estimate is not None
                    ):
                        skilled_candidates.append((score, estimate))
                selected = (
                    min(
                        skilled_candidates,
                        key=lambda item: item[0].mase
                        if item[0].mase is not None
                        else float("inf"),
                    )
                    if skilled_candidates
                    else None
                )
                predictions.append(
                    _prediction(
                        genre=genre,
                        target_axis=target_axis,
                        horizon=horizon,
                        model_name="naive",
                        is_naive=True,
                        skill_status="baseline" if selected is not None else "no_skill",
                        estimate=naive_estimate,
                        score=naive_score,
                        origin_week=latest_week,
                        training_start=history_weeks[0],
                        created_at=forecast_time,
                    )
                )
                if selected is not None:
                    selected_score, selected_estimate = selected
                    predictions.append(
                        _prediction(
                            genre=genre,
                            target_axis=target_axis,
                            horizon=horizon,
                            model_name=selected_score.model_name,
                            is_naive=False,
                            skill_status="skill",
                            estimate=selected_estimate,
                            score=selected_score,
                            origin_week=latest_week,
                            training_start=history_weeks[0],
                            created_at=forecast_time,
                        )
                    )

    ordered_predictions = tuple(
        sorted(
            predictions,
            key=lambda row: (
                row.target_axis,
                row.horizon,
                row.canonical_genre,
                row.is_naive_baseline,
            ),
        )
    )
    return ForecastBatch(
        backtest_records=backtest_records,
        model_scores=model_scores,
        predictions=ordered_predictions,
        next_up=_next_up(dataset, ordered_predictions, forecast_time),
        history_week_count=len(dataset.weeks),
    )

def _prediction(
    *,
    genre: str,
    target_axis: TargetAxis,
    horizon: int,
    model_name: ForecastModelName,
    is_naive: bool,
    skill_status: SkillStatus,
    estimate: ForecastEstimate,
    score: ModelScore,
    origin_week: date,
    training_start: date,
    created_at: datetime,
) -> ForecastPrediction:
    return ForecastPrediction(
        origin_week=origin_week,
        target_week=origin_week + timedelta(weeks=horizon),
        canonical_genre=genre,
        target_axis=target_axis,
        horizon=horizon,
        model_name=model_name,
        is_naive_baseline=is_naive,
        skill_status=skill_status,
        prediction=estimate.prediction,
        interval_low=estimate.interval_low,
        interval_high=estimate.interval_high,
        backtest_mase=score.mase,
        backtest_coverage_80=score.interval_coverage_80,
        backtest_origin_count=score.origin_count,
        training_start_week=training_start,
        training_end_week=origin_week,
        created_at=created_at,
    )


def _next_up(
    dataset: ForecastDataset,
    predictions: tuple[ForecastPrediction, ...],
    created_at: datetime,
) -> tuple[NextUpPrediction, ...]:
    chosen = {
        (prediction.canonical_genre, prediction.target_axis): prediction
        for prediction in predictions
        if prediction.horizon == 1
        and prediction.skill_status in {"skill", "no_skill"}
    }
    if not dataset.weeks:
        return ()
    origin_week = max(dataset.weeks)
    candidates: list[_NextUpCandidate] = []
    for genre in dataset.genres:
        current = dataset.row(genre, origin_week)
        conversation = chosen.get((genre, "conversation"))
        listening = chosen.get((genre, "listening"))
        if (
            current is None
            or not current.breakout_precursor
            or current.opportunity is None
            or current.opportunity_ci_low is None
            or current.opportunity_ci_high is None
            or conversation is None
            or listening is None
        ):
            continue
        predicted_opportunity = (
            conversation.prediction + listening.prediction
        ) / 2.0 - current.supply_index
        next_low = (
            conversation.interval_low + listening.interval_low
        ) / 2.0 - current.supply_index_ci_high
        next_high = (
            conversation.interval_high + listening.interval_high
        ) / 2.0 - current.supply_index_ci_low
        next_low = min(next_low, predicted_opportunity)
        next_high = max(next_high, predicted_opportunity)
        gain = predicted_opportunity - current.opportunity
        gain_low = min(gain, next_low - current.opportunity_ci_high)
        gain_high = max(gain, next_high - current.opportunity_ci_low)
        candidates.append(
            _NextUpCandidate(
                canonical_genre=genre,
                predicted_opportunity=predicted_opportunity,
                predicted_opportunity_interval_low=next_low,
                predicted_opportunity_interval_high=next_high,
                predicted_gain=gain,
                gain_interval_low=gain_low,
                gain_interval_high=gain_high,
                conversation=conversation,
                listening=listening,
            )
        )
    candidates.sort(
        key=lambda item: item.predicted_gain,
        reverse=True,
    )
    return tuple(
        NextUpPrediction(
            origin_week=origin_week,
            target_week=origin_week + timedelta(weeks=1),
            canonical_genre=candidate.canonical_genre,
            rank=rank,
            predicted_opportunity=candidate.predicted_opportunity,
            predicted_opportunity_interval_low=(
                candidate.predicted_opportunity_interval_low
            ),
            predicted_opportunity_interval_high=(
                candidate.predicted_opportunity_interval_high
            ),
            predicted_gain=candidate.predicted_gain,
            gain_interval_low=candidate.gain_interval_low,
            gain_interval_high=candidate.gain_interval_high,
            conversation_model=candidate.conversation.model_name,
            listening_model=candidate.listening.model_name,
            conversation_mase=candidate.conversation.backtest_mase,
            listening_mase=candidate.listening.backtest_mase,
            skill_status=(
                "skill"
                if candidate.conversation.skill_status == "skill"
                and candidate.listening.skill_status == "skill"
                else "no_skill"
            ),
            breakout_evidence_week=origin_week,
            created_at=created_at,
        )
        for rank, candidate in enumerate(candidates, start=1)
    )
