"""Synthetic, network-free tests for backtesting and leakage controls."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from soundcheck.forecast.backtest import BacktestConfig, run_backtest
from soundcheck.forecast.features import ForecastDataset
from soundcheck.forecast.models import ForecastHistoryRow
from soundcheck.forecast.pipeline import build_forecasts

GENRES = (
    "ambient",
    "breakcore",
    "indie rock",
    "jungle",
    "shoegaze",
    "slowcore",
)
START_WEEK = date(2025, 1, 6)


@pytest.fixture
def structured_history() -> tuple[ForecastHistoryRow, ...]:
    """Trend plus short seasonality and deterministic noise across genres."""
    rows: list[ForecastHistoryRow] = []
    for week_number in range(40):
        week_start = START_WEEK + timedelta(weeks=week_number)
        for genre_number, genre in enumerate(GENRES):
            noise = 0.025 * math.sin(week_number * 1.7 + genre_number)
            conversation = (
                -1.5
                + (0.11 + genre_number * 0.002) * week_number
                + noise
            )
            listening = (
                (1.0 if (week_number + genre_number) % 2 == 0 else -1.0)
                + 0.04 * genre_number
                + noise
            )
            supply = 0.2 * math.sin(week_number / 3.0 + genre_number)
            opportunity = (conversation + listening) / 2.0 - supply
            rows.append(
                _history_row(
                    week_start=week_start,
                    genre=genre,
                    genre_number=genre_number,
                    conversation=conversation,
                    listening=listening,
                    supply=supply,
                    opportunity=opportunity,
                    breakout_precursor=genre_number < 2,
                )
            )
    return tuple(rows)


def test_structured_backtest_beats_naive_and_reports_coverage(
    structured_history: tuple[ForecastHistoryRow, ...],
) -> None:
    dataset = ForecastDataset(structured_history)
    records, scores = run_backtest(
        dataset,
        config=BacktestConfig(
            horizons=(1,),
            target_axes=("conversation", "listening"),
            gbm_estimators=40,
        ),
        evaluated_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    ets_mase = [
        score.mase
        for score in scores
        if score.target_axis == "conversation"
        and score.model_name == "ets"
        and score.mase is not None
    ]
    gbm_mase = [
        score.mase
        for score in scores
        if score.target_axis == "listening"
        and score.model_name == "lightgbm"
        and score.mase is not None
    ]
    assert ets_mase and sum(ets_mase) / len(ets_mase) < 1.0
    assert gbm_mase and sum(gbm_mase) / len(gbm_mase) < 1.0

    model_coverages = [
        score.interval_coverage_80
        for score in scores
        if (score.target_axis, score.model_name)
        in {("conversation", "ets"), ("listening", "lightgbm")}
    ]
    assert model_coverages
    assert all(abs(coverage - 0.80) <= 0.30 for coverage in model_coverages)
    assert all(record.training_end_week <= record.origin_week for record in records)
    assert all(record.origin_week < record.target_week for record in records)


def test_features_and_training_examples_do_not_use_future_rows(
    structured_history: tuple[ForecastHistoryRow, ...],
) -> None:
    cutoff = START_WEEK + timedelta(weeks=20)
    original = ForecastDataset(structured_history)
    changed_future = tuple(
        row.model_copy(
            update={
                "conversation_index": 99_999.0,
                "listening_index": -99_999.0,
                "opportunity": 99_999.0,
            }
        )
        if row.week_start > cutoff
        else row
        for row in structured_history
    )
    mutated = ForecastDataset(changed_future)

    original_features = original.feature_vector(
        "ambient",
        "conversation",
        2,
        cutoff,
    )
    mutated_features = mutated.feature_vector(
        "ambient",
        "conversation",
        2,
        cutoff,
    )
    assert original_features == mutated_features
    assert original_features is not None
    assert original_features.max_observed_week == cutoff
    assert original_features.target_week == cutoff + timedelta(weeks=2)

    examples = mutated.training_examples(
        "conversation",
        2,
        target_cutoff_week=cutoff,
    )
    assert examples
    assert all(example.features.target_week <= cutoff for example in examples)
    assert all(
        example.features.max_observed_week <= example.features.origin_week
        < example.features.target_week
        for example in examples
    )


def test_publication_always_keeps_naive_baseline(
    structured_history: tuple[ForecastHistoryRow, ...],
) -> None:
    batch = build_forecasts(
        structured_history,
        created_at=datetime(2026, 7, 23, tzinfo=UTC),
        backtest_config=BacktestConfig(
            horizons=(1,),
            target_axes=("conversation", "listening"),
            gbm_estimators=40,
        ),
    )
    grouped: dict[tuple[str, str], list[str]] = {}
    for prediction in batch.predictions:
        grouped.setdefault(
            (prediction.canonical_genre, prediction.target_axis),
            [],
        ).append(prediction.model_name)

    assert grouped
    assert all("naive" in model_names for model_names in grouped.values())
    assert all(
        prediction.backtest_origin_count > 0
        and 0.0 <= prediction.backtest_coverage_80 <= 1.0
        and prediction.interval_low
        <= prediction.prediction
        <= prediction.interval_high
        for prediction in batch.predictions
    )
    assert all(row.canonical_genre in {"ambient", "breakcore"} for row in batch.next_up)


def test_zero_naive_scale_is_published_as_no_skill() -> None:
    constant_history = tuple(
        _history_row(
            week_start=START_WEEK + timedelta(weeks=week_number),
            genre="ambient",
            genre_number=0,
            conversation=0.0,
            listening=0.0,
            supply=0.0,
            opportunity=0.0,
            breakout_precursor=True,
        )
        for week_number in range(12)
    )
    batch = build_forecasts(
        constant_history,
        created_at=datetime(2026, 7, 23, tzinfo=UTC),
        backtest_config=BacktestConfig(
            horizons=(1,),
            target_axes=("conversation", "listening"),
            gbm_estimators=10,
        ),
    )

    assert len(batch.predictions) == 2
    assert all(
        prediction.model_name == "naive"
        and prediction.skill_status == "no_skill"
        and prediction.backtest_mase is None
        for prediction in batch.predictions
    )
    assert len(batch.next_up) == 1
    assert batch.next_up[0].skill_status == "no_skill"
    assert batch.next_up[0].conversation_mase is None
    assert batch.next_up[0].listening_mase is None


def _history_row(
    *,
    week_start: date,
    genre: str,
    genre_number: int,
    conversation: float,
    listening: float,
    supply: float,
    opportunity: float,
    breakout_precursor: bool,
) -> ForecastHistoryRow:
    return ForecastHistoryRow(
        week_start=week_start,
        canonical_genre=genre,
        conversation_index=conversation,
        listening_index=listening,
        supply_index=supply,
        supply_index_ci_low=supply - 0.1,
        supply_index_ci_high=supply + 0.1,
        discovery_gap=listening - conversation,
        conversation_ewma=conversation - 0.05,
        listening_ewma=listening * 0.8,
        supply_ewma=supply * 0.8,
        conversation_spike=False,
        listening_spike=abs(listening) > 0.95,
        supply_spike=False,
        opportunity=opportunity,
        opportunity_ci_low=opportunity - 0.2,
        opportunity_ci_high=opportunity + 0.2,
        breakout_precursor=breakout_precursor,
        genre_embedding=(
            float(genre_number == 0),
            float(genre_number == 1),
            0.5,
        ),
    )
