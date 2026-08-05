"""Build the 60-row human-label fixture from locally ingested public posts."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from soundcheck.scripts.eval_resolution import ResolutionEvalExample
from soundcheck.sql.loader import load_sql

DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
DEFAULT_OUTPUT_PATH = Path("tests/fixtures/resolution_eval.jsonl")
EVAL_SIZE = 60


def build_fixture(database_path: Path, output_path: Path) -> int:
    """Select actual raw posts and overwrite the generated unlabeled fixture."""
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_post_artist_resolution.sql"))
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_resolution_eval_candidates.sql"),
            [EVAL_SIZE],
        ).fetchall()
    if len(rows) != EVAL_SIZE:
        msg = f"expected {EVAL_SIZE} ingested posts, found {len(rows)}"
        raise RuntimeError(msg)
    examples = tuple(
        ResolutionEvalExample(
            example_id=f"resolution-{index:03d}",
            post_uri=row[0],
            text=row[1],
            link_urls=tuple(row[2]),
            predicted_artist_mbid=row[3],
            predicted_artist_name=row[4],
            predicted_method=row[5],
            predicted_join_key_type=row[6],
            label_should_resolve=None,
            label_artist_mbid=None,
            label_artist_name=None,
        )
        for index, row in enumerate(rows, start=1)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            f"{example.model_dump_json(exclude_none=False)}\n"
            for example in examples
        ),
        encoding="utf-8",
    )
    return len(examples)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    count = build_fixture(args.database, args.output)
    print(f"wrote {count} actual ingested examples to {args.output}")


if __name__ == "__main__":
    main()
