"""Report persisted taxonomy-v2 coverage as a table or JSON Lines."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from soundcheck.metrics.coverage import GenreCoverageRow
from soundcheck.metrics.coverage_run import DEFAULT_DATABASE_PATH
from soundcheck.metrics.coverage_storage import (
    initialize_coverage_storage,
    load_coverage_rows,
)
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy


class CoverageMacroSummary(BaseModel):
    """Eligibility and missing-axis counts for one macro family."""

    model_config = ConfigDict(frozen=True)

    record_type: Literal["macro_family"] = "macro_family"
    week_start: date
    macro_family_id: str
    macro_family_name: str
    genre_count: int
    eligibility_counts: dict[str, int]
    listening_missing: int
    conversation_missing: int
    supply_missing: int


def select_report_rows(
    rows: tuple[GenreCoverageRow, ...],
    *,
    week: date | None,
    all_weeks: bool,
) -> tuple[GenreCoverageRow, ...]:
    """Select an explicit week or, by default, the latest computed week."""

    if all_weeks or not rows:
        return rows
    selected_week = week or max(row.week_start for row in rows)
    return tuple(row for row in rows if row.week_start == selected_week)


def summarize_macro_families(
    rows: Iterable[GenreCoverageRow],
) -> tuple[CoverageMacroSummary, ...]:
    """Aggregate eligibility and missingness without filling source measures."""

    grouped: dict[tuple[date, str, str], list[GenreCoverageRow]] = defaultdict(list)
    for row in rows:
        grouped[
            (row.week_start, row.macro_family_id, row.macro_family_name)
        ].append(row)
    summaries = []
    for (week, macro_id, macro_name), genre_rows in sorted(grouped.items()):
        summaries.append(
            CoverageMacroSummary(
                week_start=week,
                macro_family_id=macro_id,
                macro_family_name=macro_name,
                genre_count=len(genre_rows),
                eligibility_counts=dict(
                    sorted(
                        Counter(row.eligibility_state for row in genre_rows).items()
                    )
                ),
                listening_missing=sum(row.listening_missing for row in genre_rows),
                conversation_missing=sum(
                    row.conversation_missing for row in genre_rows
                ),
                supply_missing=sum(row.supply_missing for row in genre_rows),
            )
        )
    return tuple(summaries)


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _table(headers: tuple[str, ...], rows: Iterable[tuple[object, ...]]) -> str:
    materialized = [tuple(_display(value) for value in row) for row in rows]
    widths = [
        max(len(header), *(len(row[index]) for row in materialized))
        for index, header in enumerate(headers)
    ]
    header_line = "  ".join(
        header.ljust(widths[index]) for index, header in enumerate(headers)
    )
    rule = "  ".join("-" * width for width in widths)
    body = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in materialized
    ]
    return "\n".join((header_line, rule, *body))


def render_table(rows: tuple[GenreCoverageRow, ...]) -> str:
    """Render genre evidence plus macro-family eligibility summaries."""

    if not rows:
        return "No coverage rows have been computed."
    genre_table = _table(
        (
            "week",
            "genre",
            "status",
            "LF tag",
            "LF artists",
            "valid LF",
            "MB releases",
            "BS posts",
            "resolution",
            "overlap",
        ),
        (
            (
                row.week_start,
                row.display_name,
                row.eligibility_state,
                row.lastfm_tag_available,
                row.unique_lastfm_artists,
                row.artists_with_consecutive_valid_snapshots,
                row.musicbrainz_release_group_count,
                row.resolved_bluesky_post_count,
                row.resolution_rate,
                row.cross_source_overlap,
            )
            for row in rows
        ),
    )
    macro_table = _table(
        (
            "week",
            "macro family",
            "genres",
            "ready",
            "collecting",
            "unsupported",
            "missing L/C/S",
        ),
        (
            (
                summary.week_start,
                summary.macro_family_name,
                summary.genre_count,
                summary.eligibility_counts.get("ready", 0),
                summary.eligibility_counts.get("collecting_history", 0),
                summary.eligibility_counts.get("unsupported", 0),
                (
                    f"{summary.listening_missing}/"
                    f"{summary.conversation_missing}/"
                    f"{summary.supply_missing}"
                ),
            )
            for summary in summarize_macro_families(rows)
        ),
    )
    return f"GENRE COVERAGE\n{genre_table}\n\nMACRO-FAMILY SUMMARY\n{macro_table}"


def render_jsonlines(rows: tuple[GenreCoverageRow, ...]) -> str:
    """Render one line per genre followed by one line per macro family."""

    lines = []
    for row in rows:
        payload = {"record_type": "genre", **row.model_dump(mode="json")}
        lines.append(json.dumps(payload, sort_keys=True))
    lines.extend(
        json.dumps(summary.model_dump(mode="json"), sort_keys=True)
        for summary in summarize_macro_families(rows)
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report taxonomy-v2 source coverage.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--format", choices=("table", "jsonl"), default="table")
    parser.add_argument("--week", type=date.fromisoformat)
    parser.add_argument("--all-weeks", action="store_true")
    args = parser.parse_args()
    taxonomy = load_taxonomy(args.taxonomy)
    initialize_coverage_storage(args.database)
    rows = load_coverage_rows(args.database, taxonomy.taxonomy_version)
    selected = select_report_rows(
        rows,
        week=args.week,
        all_weeks=args.all_weeks,
    )
    print(render_jsonlines(selected) if args.format == "jsonl" else render_table(selected))


if __name__ == "__main__":
    main()
