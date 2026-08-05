"""Run taxonomy-v2 forecasts and print the complete family-aware score ledger."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from soundcheck.forecast.v2_models import ForecastBatchV2, ModelScoreV2
from soundcheck.forecast.v2_pipeline import (
    MINIMUM_TRAINING_WEEKS_V2,
    build_forecasts_v2,
)
from soundcheck.forecast.v2_storage import DuckDBForecastV2Store
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")


class ForecastV2Settings(BaseModel):
    """Validated paths for a version-isolated forecast run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_path: Path = DEFAULT_DATABASE_PATH
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH


class ModelScoreV2Event(BaseModel):
    """One row from the complete v2 validation ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["forecast_v2_model_score"] = "forecast_v2_model_score"
    score: ModelScoreV2


class ForecastV2Completion(BaseModel):
    """Terminal counts with explicit cold-start status totals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["forecast_v2_complete"] = "forecast_v2_complete"
    taxonomy_version: str
    history_weeks: int
    minimum_training_weeks: int
    backtest_rows: int
    model_score_rows: int
    prediction_rows: int
    forecast_status_counts: dict[str, int]


async def async_main(settings: ForecastV2Settings) -> ForecastBatchV2:
    """Load mart v2, compute backtests, and replace only this taxonomy version."""
    taxonomy = load_taxonomy(settings.taxonomy_path)
    store = DuckDBForecastV2Store(settings.database_path)
    await store.initialize()
    history = await store.load_history(taxonomy.taxonomy_version)
    batch = await asyncio.to_thread(
        build_forecasts_v2,
        history,
        taxonomy,
    )
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
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    batch = asyncio.run(
        async_main(
            ForecastV2Settings(
                database_path=args.database,
                taxonomy_path=args.taxonomy,
            )
        )
    )
    for score in batch.model_scores:
        _emit(ModelScoreV2Event(score=score))
    _emit(
        ForecastV2Completion(
            taxonomy_version=batch.taxonomy_version,
            history_weeks=batch.history_week_count,
            minimum_training_weeks=MINIMUM_TRAINING_WEEKS_V2,
            backtest_rows=len(batch.backtest_records),
            model_score_rows=len(batch.model_scores),
            prediction_rows=len(batch.predictions),
            forecast_status_counts=dict(
                sorted(
                    Counter(
                        row.forecast_status for row in batch.predictions
                    ).items()
                )
            ),
        )
    )


if __name__ == "__main__":
    main()
