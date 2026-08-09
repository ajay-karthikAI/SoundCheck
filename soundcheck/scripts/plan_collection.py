"""Print the taxonomy-v2 collection request, runtime, and sharding plan."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from soundcheck.ingest.scaling import (
    DEFAULT_SCALING_CONFIG_PATH,
    CollectionPlan,
    build_collection_plan,
)
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH


def render_table(plan: CollectionPlan) -> str:
    """Render a concise operator-readable dry-run plan."""

    rows = (
        plan.lastfm,
        plan.musicbrainz,
    )
    lines = [
        "COLLECTION DRY-RUN PLAN",
        (
            "source       tags  tag req  dedup artists  MB pages  cache assumption  "
            "runtime  shards  per shard"
        ),
        (
            "-----------  ----  -------  -------------  --------  ----------------  "
            "-------  ------  ---------"
        ),
    ]
    for row in rows:
        tag_requests = "—" if row.tag_requests is None else str(row.tag_requests)
        artists = (
            "—"
            if row.expected_deduplicated_artist_count is None
            else str(row.expected_deduplicated_artist_count)
        )
        pages = "—" if row.expected_pages is None else str(row.expected_pages)
        lines.append(
            f"{row.source:<11}  {row.tag_count:>4}  {tag_requests:>7}  "
            f"{artists:>13}  {pages:>8}  "
            f"{row.cache_hit_assumption:>15.0%}  "
            f"{row.estimated_runtime_seconds / 60:>6.1f}m  "
            f"{row.shard_count:>6}  "
            f"{row.estimated_seconds_per_shard / 60:>8.1f}m"
        )
    lines.extend(
        (
            "",
            f"Last.fm tags ({plan.lastfm.tag_count}): {', '.join(plan.lastfm.tags)}",
            (
                f"MusicBrainz tags ({plan.musicbrainz.tag_count}): "
                f"{', '.join(plan.musicbrainz.tags)}"
            ),
            "",
            (
                f"Incremental MusicBrainz window: {plan.incremental_start_date} "
                f"through {plan.incremental_end_date}"
            ),
            (
                "Cache-hit assumptions affect planning only; clients still inspect "
                "the disk cache per request."
            ),
        )
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_SCALING_CONFIG_PATH)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--format", choices=("table", "json", "github"), default="table")
    args = parser.parse_args()
    plan = build_collection_plan(
        database_path=args.database,
        taxonomy_path=args.taxonomy,
        config_path=args.config,
        as_of=args.as_of,
    )
    if args.format == "json":
        print(json.dumps(plan.model_dump(mode="json"), sort_keys=True))
    elif args.format == "github":
        iso = args.as_of.isocalendar()
        print(f"lastfm_shard_count={plan.lastfm.shard_count}")
        print(f"lastfm_run_key=lastfm-{iso.year}-W{iso.week:02d}")
        print(f"musicbrainz_shard_count={plan.musicbrainz.shard_count}")
    else:
        print(render_table(plan))


if __name__ == "__main__":
    main()
