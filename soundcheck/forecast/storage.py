"""DuckDB history loading and atomic forecast-artifact replacement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.forecast.models import (
    BacktestRecord,
    ForecastBatch,
    ForecastHistoryRow,
    ForecastPrediction,
    ModelScore,
    NextUpPrediction,
)
from soundcheck.sql.loader import load_sql


class DuckDBForecastStore:
    """Read Phase 4 marts and replace all Phase 5 tables transactionally."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_history(self) -> tuple[ForecastHistoryRow, ...]:
        return await asyncio.to_thread(_load_history, self._database_path)

    async def replace(self, batch: ForecastBatch) -> tuple[int, int, int, int]:
        await asyncio.to_thread(_replace, self._database_path, batch)
        return (
            len(batch.backtest_records),
            len(batch.model_scores),
            len(batch.predictions),
            len(batch.next_up),
        )


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_genre_resolution.sql"))
        connection.execute(load_sql("create_mart_metrics.sql"))
        connection.execute(load_sql("create_fcst_tables.sql"))


def _load_history(database_path: Path) -> tuple[ForecastHistoryRow, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(load_sql("select_forecast_history.sql")).fetchall()
    return tuple(
        ForecastHistoryRow(
            week_start=row[0],
            canonical_genre=row[1],
            conversation_index=row[2],
            listening_index=row[3],
            supply_index=row[4],
            supply_index_ci_low=row[5],
            supply_index_ci_high=row[6],
            discovery_gap=row[7],
            conversation_ewma=row[8],
            listening_ewma=row[9],
            supply_ewma=row[10],
            conversation_spike=row[11],
            listening_spike=row[12],
            supply_spike=row[13],
            opportunity=row[14],
            opportunity_ci_low=row[15],
            opportunity_ci_high=row[16],
            breakout_precursor=row[17],
            genre_embedding=tuple(float(value) for value in row[18]),
        )
        for row in rows
    )


def _replace(database_path: Path, batch: ForecastBatch) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            connection.execute(load_sql("delete_fcst_tables.sql"))
            _insert_rows(
                connection,
                "insert_fcst_backtest_ledger.sql",
                [_backtest_row(record) for record in batch.backtest_records],
            )
            _insert_rows(
                connection,
                "insert_fcst_model_scores.sql",
                [_score_row(score) for score in batch.model_scores],
            )
            _insert_rows(
                connection,
                "insert_fcst_predictions.sql",
                [_prediction_row(prediction) for prediction in batch.predictions],
            )
            _insert_rows(
                connection,
                "insert_fcst_next_up.sql",
                [_next_up_row(prediction) for prediction in batch.next_up],
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _insert_rows(
    connection: duckdb.DuckDBPyConnection,
    statement_name: str,
    rows: list[tuple[object, ...]],
) -> None:
    if rows:
        connection.executemany(load_sql(statement_name), rows)


def _backtest_row(record: BacktestRecord) -> tuple[object, ...]:
    return (
        record.canonical_genre,
        record.target_axis,
        record.horizon,
        record.model_name,
        record.origin_week,
        record.target_week,
        record.training_start_week,
        record.training_end_week,
        record.training_weeks,
        record.actual,
        record.prediction,
        record.interval_low,
        record.interval_high,
        record.absolute_error,
        record.covered_80,
    )


def _score_row(score: ModelScore) -> tuple[object, ...]:
    return (
        score.canonical_genre,
        score.target_axis,
        score.horizon,
        score.model_name,
        score.backtest_start_week,
        score.backtest_end_week,
        score.origin_count,
        score.mae,
        score.naive_mae,
        score.mase,
        score.interval_coverage_80,
        score.mean_interval_width,
        score.score_status,
        score.evaluated_at,
    )


def _prediction_row(prediction: ForecastPrediction) -> tuple[object, ...]:
    return (
        prediction.origin_week,
        prediction.target_week,
        prediction.canonical_genre,
        prediction.target_axis,
        prediction.horizon,
        prediction.model_name,
        prediction.is_naive_baseline,
        prediction.skill_status,
        prediction.prediction,
        prediction.interval_low,
        prediction.interval_high,
        prediction.backtest_mase,
        prediction.backtest_coverage_80,
        prediction.backtest_origin_count,
        prediction.training_start_week,
        prediction.training_end_week,
        prediction.created_at,
    )


def _next_up_row(prediction: NextUpPrediction) -> tuple[object, ...]:
    return (
        prediction.origin_week,
        prediction.target_week,
        prediction.canonical_genre,
        prediction.rank,
        prediction.predicted_opportunity,
        prediction.predicted_opportunity_interval_low,
        prediction.predicted_opportunity_interval_high,
        prediction.predicted_gain,
        prediction.gain_interval_low,
        prediction.gain_interval_high,
        prediction.conversation_model,
        prediction.listening_model,
        prediction.conversation_mase,
        prediction.listening_mase,
        prediction.skill_status,
        prediction.breakout_evidence_week,
        prediction.created_at,
    )
