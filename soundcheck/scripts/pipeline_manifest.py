"""Start and finish durable weekly-pipeline run manifests in DuckDB."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from soundcheck.sql.loader import load_sql


class PipelineCounts(BaseModel):
    """Observed row counts for one pipeline execution window."""

    model_config = ConfigDict(frozen=True)

    bluesky_posts_ingested: int = Field(ge=0)
    bluesky_engagement_snapshots_ingested: int = Field(ge=0)
    lastfm_tag_snapshots_ingested: int = Field(ge=0)
    lastfm_artist_snapshots_ingested: int = Field(ge=0)
    musicbrainz_release_groups_ingested: int = Field(ge=0)
    resolution_posts_attempted: int = Field(ge=0)
    resolution_links_resolved: int = Field(ge=0)
    metric_rows: int = Field(ge=0)
    forecast_rows: int = Field(ge=0)
    brief_rows: int = Field(ge=0)

    @property
    def resolution_rate(self) -> float | None:
        if self.resolution_posts_attempted == 0:
            return None
        return min(
            1.0,
            self.resolution_links_resolved
            / self.resolution_posts_attempted,
        )


def begin_pipeline_run(
    database_path: Path,
    *,
    run_id: str,
    run_kind: Literal["daily", "weekly"],
    trigger_name: str,
    git_sha: str | None,
    started_at: datetime | None = None,
) -> None:
    """Initialize source tables and persist a running manifest row."""
    start = (started_at or datetime.now(UTC)).astimezone(UTC)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement_name in (
            "create_raw_bluesky_posts.sql",
            "create_raw_bluesky_cursors.sql",
            "create_raw_bluesky_engagement.sql",
            "create_raw_lastfm_snapshots.sql",
            "create_raw_mb_release_groups.sql",
            "create_stg_post_artist_resolution.sql",
            "create_stg_genre_resolution.sql",
            "create_mart_metrics.sql",
            "create_mart_evidence.sql",
            "create_mart_scene_map.sql",
            "create_fcst_tables.sql",
            "create_mart_briefs.sql",
            "create_mart_pipeline_runs.sql",
        ):
            connection.execute(load_sql(statement_name))
        connection.execute(
            load_sql("insert_pipeline_run_started.sql"),
            (run_id, run_kind, trigger_name, git_sha, start),
        )


def finish_pipeline_run(
    database_path: Path,
    *,
    run_id: str,
    status: Literal["success", "failed"],
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> PipelineCounts:
    """Measure the run window and atomically finish its manifest."""
    end = (completed_at or datetime.now(UTC)).astimezone(UTC)
    with duckdb.connect(str(database_path)) as connection:
        started_row = connection.execute(
            load_sql("select_pipeline_run_started_at.sql"),
            (run_id,),
        ).fetchone()
        if started_row is None:
            msg = f"pipeline run not found: {run_id}"
            raise ValueError(msg)
        start = started_row[0]
        parameters: list[datetime] = []
        for _ in range(10):
            parameters.extend((start, end))
        row = connection.execute(
            load_sql("select_pipeline_run_counts.sql"),
            parameters,
        ).fetchone()
        if row is None:
            raise RuntimeError("pipeline count query returned no row")
        counts = PipelineCounts(
            bluesky_posts_ingested=row[0],
            bluesky_engagement_snapshots_ingested=row[1],
            lastfm_tag_snapshots_ingested=row[2],
            lastfm_artist_snapshots_ingested=row[3],
            musicbrainz_release_groups_ingested=row[4],
            resolution_posts_attempted=row[5],
            resolution_links_resolved=row[6],
            metric_rows=row[7],
            forecast_rows=row[8],
            brief_rows=row[9],
        )
        wall_time_seconds = max(0.0, (end - start).total_seconds())
        connection.execute(
            load_sql("update_pipeline_run_finished.sql"),
            (
                status,
                end,
                wall_time_seconds,
                counts.bluesky_posts_ingested,
                counts.bluesky_engagement_snapshots_ingested,
                counts.lastfm_tag_snapshots_ingested,
                counts.lastfm_artist_snapshots_ingested,
                counts.musicbrainz_release_groups_ingested,
                counts.resolution_posts_attempted,
                counts.resolution_links_resolved,
                counts.resolution_rate,
                counts.metric_rows,
                counts.forecast_rows,
                counts.brief_rows,
                error_message,
                run_id,
            ),
        )
    return counts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/soundcheck.duckdb"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    begin = subparsers.add_parser("begin")
    begin.add_argument("--run-id", required=True)
    begin.add_argument(
        "--run-kind",
        choices=("daily", "weekly"),
        required=True,
    )
    begin.add_argument("--trigger", required=True)
    begin.add_argument("--git-sha")
    finish = subparsers.add_parser("finish")
    finish.add_argument("--run-id", required=True)
    finish.add_argument(
        "--status",
        choices=("success", "failed"),
        required=True,
    )
    finish.add_argument("--error-message")
    return parser


def main() -> None:
    """CLI entrypoint for workflow steps."""
    args = _build_parser().parse_args()
    if args.command == "begin":
        begin_pipeline_run(
            args.database,
            run_id=args.run_id,
            run_kind=args.run_kind,
            trigger_name=args.trigger,
            git_sha=args.git_sha,
        )
        payload: dict[str, object] = {
            "event": "pipeline_manifest_started",
            "run_id": args.run_id,
        }
    else:
        counts = finish_pipeline_run(
            args.database,
            run_id=args.run_id,
            status=args.status,
            error_message=args.error_message,
        )
        payload = {
            "event": "pipeline_manifest_finished",
            "run_id": args.run_id,
            "status": args.status,
            **counts.model_dump(),
            "resolution_rate": counts.resolution_rate,
        }
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
