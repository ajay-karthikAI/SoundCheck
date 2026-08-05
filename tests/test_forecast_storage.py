"""DuckDB contract tests for the four Phase 5 forecast artifacts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from soundcheck.forecast.models import (
    BacktestRecord,
    ForecastBatch,
    ForecastPrediction,
    ModelScore,
    NextUpPrediction,
)
from soundcheck.forecast.storage import DuckDBForecastStore
from soundcheck.sql.loader import load_sql


@pytest.mark.asyncio
async def test_forecast_artifacts_replace_atomically(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast.duckdb"
    store = DuckDBForecastStore(database_path)
    await store.initialize()
    batch = _forecast_batch()

    assert await store.replace(batch) == (1, 1, 1, 1)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        counts = connection.execute(
            load_sql("summarize_fcst_tables.sql")
        ).fetchone()
    assert counts == (1, 1, 1, 1)

    empty = ForecastBatch(
        backtest_records=(),
        model_scores=(),
        predictions=(),
        next_up=(),
        history_week_count=0,
    )
    assert await store.replace(empty) == (0, 0, 0, 0)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        remaining = connection.execute(
            load_sql("summarize_fcst_tables.sql")
        ).fetchone()
    assert remaining == (0, 0, 0, 0)


def _forecast_batch() -> ForecastBatch:
    evaluated_at = datetime(2026, 7, 23, tzinfo=UTC)
    origin_week = date(2026, 7, 13)
    target_week = date(2026, 7, 20)
    record = BacktestRecord(
        canonical_genre="shoegaze",
        target_axis="listening",
        horizon=1,
        model_name="naive",
        origin_week=origin_week,
        target_week=target_week,
        training_start_week=date(2026, 5, 25),
        training_end_week=origin_week,
        training_weeks=8,
        actual=0.8,
        prediction=0.7,
        interval_low=0.5,
        interval_high=0.9,
        absolute_error=0.1,
        covered_80=True,
    )
    score = ModelScore(
        canonical_genre="shoegaze",
        target_axis="listening",
        horizon=1,
        model_name="naive",
        backtest_start_week=target_week,
        backtest_end_week=target_week,
        origin_count=1,
        mae=0.1,
        naive_mae=0.1,
        mase=1.0,
        interval_coverage_80=1.0,
        mean_interval_width=0.4,
        score_status="scored",
        evaluated_at=evaluated_at,
    )
    prediction = ForecastPrediction(
        origin_week=target_week,
        target_week=date(2026, 7, 27),
        canonical_genre="shoegaze",
        target_axis="listening",
        horizon=1,
        model_name="naive",
        is_naive_baseline=True,
        skill_status="no_skill",
        prediction=0.8,
        interval_low=0.6,
        interval_high=1.0,
        backtest_mase=1.0,
        backtest_coverage_80=1.0,
        backtest_origin_count=1,
        training_start_week=date(2026, 5, 25),
        training_end_week=target_week,
        created_at=evaluated_at,
    )
    next_up = NextUpPrediction(
        origin_week=target_week,
        target_week=date(2026, 7, 27),
        canonical_genre="shoegaze",
        rank=1,
        predicted_opportunity=0.9,
        predicted_opportunity_interval_low=0.6,
        predicted_opportunity_interval_high=1.2,
        predicted_gain=0.2,
        gain_interval_low=-0.1,
        gain_interval_high=0.5,
        conversation_model="naive",
        listening_model="naive",
        conversation_mase=1.0,
        listening_mase=1.0,
        skill_status="no_skill",
        breakout_evidence_week=target_week,
        created_at=evaluated_at,
    )
    return ForecastBatch(
        backtest_records=(record,),
        model_scores=(score,),
        predictions=(prediction,),
        next_up=(next_up,),
        history_week_count=9,
    )
