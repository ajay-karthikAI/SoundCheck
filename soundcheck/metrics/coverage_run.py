"""Compute taxonomy-v2 source coverage from existing DuckDB evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from soundcheck.metrics.coverage import (
    CoverageBatch,
    compute_coverage,
    load_coverage_thresholds,
)
from soundcheck.metrics.coverage_storage import (
    initialize_coverage_storage,
    load_coverage_evidence,
    replace_coverage_batch,
)
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
DEFAULT_THRESHOLDS_PATH = Path("config/coverage.yml")


class CoverageCompletion(BaseModel):
    """Validated machine-readable terminal event."""

    model_config = ConfigDict(frozen=True)

    event: str = "coverage_complete"
    taxonomy_version: str
    start_week: date | None
    end_week: date | None
    genre_week_rows: int
    eligibility_counts_latest_week: dict[str, int]


def run_coverage(
    *,
    database_path: Path,
    taxonomy_path: Path,
    thresholds_path: Path,
    computed_at: datetime,
    start_week: date | None = None,
    end_week: date | None = None,
) -> CoverageBatch:
    """Read evidence, compute the complete grid, and atomically persist it."""

    taxonomy = load_taxonomy(taxonomy_path)
    thresholds = load_coverage_thresholds(thresholds_path)
    initialize_coverage_storage(database_path)
    evidence = load_coverage_evidence(database_path)
    batch = compute_coverage(
        taxonomy,
        thresholds,
        evidence,
        computed_at=computed_at,
        start_week=start_week,
        end_week=end_week,
    )
    replace_coverage_batch(database_path, batch)
    return batch


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--computed-at must include a UTC offset")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute source coverage without enabling new collectors or surfaces."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS_PATH)
    parser.add_argument("--start-week", type=_parse_date)
    parser.add_argument("--end-week", type=_parse_date)
    parser.add_argument("--computed-at", type=_parse_timestamp)
    args = parser.parse_args()
    batch = run_coverage(
        database_path=args.database,
        taxonomy_path=args.taxonomy,
        thresholds_path=args.thresholds,
        computed_at=args.computed_at or datetime.now(UTC),
        start_week=args.start_week,
        end_week=args.end_week,
    )
    latest_rows = (
        tuple(row for row in batch.rows if row.week_start == batch.end_week)
        if batch.end_week is not None
        else ()
    )
    completion = CoverageCompletion(
        taxonomy_version=batch.taxonomy_version,
        start_week=batch.start_week,
        end_week=batch.end_week,
        genre_week_rows=len(batch.rows),
        eligibility_counts_latest_week=dict(
            sorted(Counter(row.eligibility_state for row in latest_rows).items())
        ),
    )
    print(json.dumps(completion.model_dump(mode="json"), sort_keys=True))


if __name__ == "__main__":
    main()
