"""Version-isolated DuckDB persistence for taxonomy-v2 forecasts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.forecast.v2_models import (
    BacktestRecordV2,
    ForecastBatchV2,
    ForecastHistoryRowV2,
    ForecastPredictionV2,
    ModelScoreV2,
)
from soundcheck.sql.loader import load_sql


class DuckDBForecastV2Store:
    """Read v2 marts and replace only one taxonomy version's forecasts."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_history(
        self,
        taxonomy_version: str,
    ) -> tuple[ForecastHistoryRowV2, ...]:
        return await asyncio.to_thread(
            _load_history,
            self._database_path,
            taxonomy_version,
        )

    async def replace(self, batch: ForecastBatchV2) -> tuple[int, int, int]:
        await asyncio.to_thread(_replace, self._database_path, batch)
        return (
            len(batch.backtest_records),
            len(batch.model_scores),
            len(batch.predictions),
        )


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement in (
            "create_mart_genre_coverage_v2.sql",
            "create_mart_metrics.sql",
            "create_mart_metrics_v2.sql",
            "create_mart_metric_versions.sql",
            "create_fcst_tables_v2.sql",
        ):
            connection.execute(load_sql(statement))


def _load_history(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[ForecastHistoryRowV2, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_forecast_history_v2.sql"),
            [taxonomy_version],
        ).fetchall()
    return tuple(
        ForecastHistoryRowV2(
            taxonomy_version=row[0],
            week_start=row[1],
            genre_id=row[2],
            display_name=row[3],
            macro_family_id=row[4],
            parent_genre_id=row[5],
            taxonomy_status=row[6],
            coverage_state=row[7],
            estimate_eligible=row[8],
            context=row[9],
            conversation=row[10],
            listening=row[11],
            supply=row[12],
            discovery_gap=row[13],
            opportunity=row[14],
            conversation_ewma=row[15],
            listening_ewma=row[16],
            supply_ewma=row[17],
            conversation_spike=row[18],
            listening_spike=row[19],
            supply_spike=row[20],
            conversation_effective_n=row[21],
            listening_effective_n=row[22],
        )
        for row in rows
    )


def _replace(database_path: Path, batch: ForecastBatchV2) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            for statement in (
                "delete_fcst_backtest_v2_version.sql",
                "delete_fcst_model_scores_v2_version.sql",
                "delete_fcst_predictions_v2_version.sql",
                "delete_fcst_next_up_v2_version.sql",
            ):
                connection.execute(
                    load_sql(statement),
                    [batch.taxonomy_version],
                )
            _insert_rows(
                connection,
                "insert_fcst_backtest_ledger_v2.sql",
                [_backtest_row(row) for row in batch.backtest_records],
            )
            _insert_rows(
                connection,
                "insert_fcst_model_score_v2.sql",
                [_score_row(row) for row in batch.model_scores],
            )
            _insert_rows(
                connection,
                "insert_fcst_prediction_v2.sql",
                [_prediction_row(row) for row in batch.predictions],
            )
            connection.execute(
                load_sql("refresh_fcst_next_up_v2.sql"),
                [batch.taxonomy_version] * 2,
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


def _backtest_row(row: BacktestRecordV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.genre_id,
        row.macro_family_id,
        row.popularity_tier,
        row.context,
        row.target_axis,
        row.horizon,
        row.model_name,
        row.origin_week,
        row.target_week,
        row.training_start_week,
        row.training_end_week,
        row.training_weeks,
        row.max_feature_week,
        row.actual,
        row.prediction,
        row.interval_low,
        row.interval_high,
        row.absolute_error,
        row.covered_80,
    )


def _score_row(row: ModelScoreV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.validation_scope,
        row.validation_group_id,
        row.genre_id,
        row.macro_family_id,
        row.popularity_tier,
        row.context,
        row.target_axis,
        row.horizon,
        row.model_name,
        row.backtest_start_week,
        row.backtest_end_week,
        row.origin_count,
        row.mae,
        row.naive_mae,
        row.mase,
        row.interval_coverage_80,
        row.mean_interval_width,
        row.score_status,
        row.evaluated_at,
    )


def _prediction_row(row: ForecastPredictionV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.origin_week,
        row.target_week,
        row.genre_id,
        row.display_name,
        row.macro_family_id,
        row.popularity_tier,
        row.context,
        row.target_axis,
        row.horizon,
        row.forecast_status,
        row.model_name,
        row.prediction,
        row.interval_low,
        row.interval_high,
        row.backtest_mase,
        row.backtest_coverage_80,
        row.backtest_score_status,
        row.family_backtest_mase,
        row.family_backtest_coverage_80,
        row.family_backtest_score_status,
        row.naive_prediction,
        row.naive_interval_low,
        row.naive_interval_high,
        row.naive_backtest_mase,
        row.naive_backtest_coverage_80,
        row.naive_backtest_score_status,
        row.valid_training_weeks,
        row.training_start_week,
        row.training_end_week,
        row.created_at,
    )
