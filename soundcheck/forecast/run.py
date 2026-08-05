"""Run the validated forecast batch and print the complete model-score ledger."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from soundcheck.forecast.models import ForecastBatch, ModelScore, NextUpPrediction
from soundcheck.forecast.pipeline import build_forecasts
from soundcheck.forecast.storage import DuckDBForecastStore


class ForecastSettings(BaseModel):
    """Validated forecast batch settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")


class ModelScoreEvent(BaseModel):
    """One printed entry from the full per-model score ledger."""

    model_config = ConfigDict(frozen=True)

    event: Literal["model_score"] = "model_score"
    score: ModelScore


class NextUpEvent(BaseModel):
    """Printed marquee ranking with inherited uncertainty."""

    model_config = ConfigDict(frozen=True)

    event: Literal["next_up"] = "next_up"
    rows: tuple[NextUpPrediction, ...]


class ForecastCompletion(BaseModel):
    """Validated terminal status, including honest cold-start state."""

    model_config = ConfigDict(frozen=True)

    event: Literal["forecast_complete"] = "forecast_complete"
    status: Literal["ready", "insufficient_history"]
    history_weeks: int
    minimum_training_weeks: int
    backtest_rows: int
    model_score_rows: int
    prediction_rows: int
    next_up_rows: int


async def async_main(settings: ForecastSettings) -> ForecastBatch:
    """Load mart history, calculate forecasts, and replace fcst_ artifacts."""
    store = DuckDBForecastStore(settings.database_path)
    await store.initialize()
    history = await store.load_history()
    batch = await asyncio.to_thread(build_forecasts, history)
    await store.replace(batch)
    return batch


def _emit(model: BaseModel) -> None:
    print(
        json.dumps(
            model.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    batch = asyncio.run(
        async_main(ForecastSettings(database_path=args.database))
    )
    for score in batch.model_scores:
        _emit(ModelScoreEvent(score=score))
    _emit(NextUpEvent(rows=batch.next_up))
    _emit(
        ForecastCompletion(
            status="ready" if batch.model_scores else "insufficient_history",
            history_weeks=batch.history_week_count,
            minimum_training_weeks=8,
            backtest_rows=len(batch.backtest_records),
            model_score_rows=len(batch.model_scores),
            prediction_rows=len(batch.predictions),
            next_up_rows=len(batch.next_up),
        )
    )


if __name__ == "__main__":
    main()
