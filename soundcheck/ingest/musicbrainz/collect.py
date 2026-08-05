"""Collect MusicBrainz release groups with stable insert-on-first-sight storage.

This deliberately differs from Last.fm. Last.fm lifetime totals require a new
append-only snapshot every run so later metrics can use deltas. MusicBrainz
release-group first-release dates are treated as stable supply facts here, so
an MBID is inserted only on first sight and is never refreshed or overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, model_validator

from soundcheck.config import DEFAULT_GENRES_PATH, load_genres
from soundcheck.ingest.checkpoints import (
    CollectionCheckpointStore,
    CollectionRunMetadata,
)
from soundcheck.ingest.http import DiskJsonCache
from soundcheck.ingest.musicbrainz.client import (
    MUSICBRAINZ_CACHE_MAX_AGE_SECONDS,
    MusicBrainzClient,
    musicbrainz_user_agent,
)
from soundcheck.ingest.musicbrainz.models import (
    ArtistCreditRecord,
    RawMusicBrainzReleaseGroup,
    ReleaseGroupSearchResponse,
    TagCountRecord,
)
from soundcheck.ingest.musicbrainz.resumable import (
    collect_musicbrainz_shard,
    finalize_musicbrainz_run,
)
from soundcheck.ingest.musicbrainz.storage import MusicBrainzReleaseGroupWriter
from soundcheck.ingest.scaling import (
    DEFAULT_SCALING_CONFIG_PATH,
    load_scaling_config,
)
from soundcheck.taxonomy import load_taxonomy

RELEASE_GROUP_PAGE_SIZE = 100
RELEASE_GROUP_INCLUDES = "genres+tags+artist-credits"


class MusicBrainzCollectSettings(BaseModel):
    """Validated incremental or backfill settings."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["incremental", "backfill"]
    start_date: date
    end_date: date
    database_path: Path = Path("data/soundcheck.duckdb")
    genres_path: Path = DEFAULT_GENRES_PATH
    cache_directory: Path = Path(".cache/musicbrainz")
    scaling_config_path: Path = DEFAULT_SCALING_CONFIG_PATH
    run_key: str
    phase: Literal["all", "collect", "finalize"] = "all"
    shard_count: int = 1
    shard_index: int = 0

    @model_validator(mode="after")
    def validate_window(self) -> MusicBrainzCollectSettings:
        if self.start_date > self.end_date:
            msg = "start_date must not be after end_date"
            raise ValueError(msg)
        if self.shard_count <= 0:
            raise ValueError("shard_count must be positive")
        if self.shard_index < 0 or self.shard_index >= self.shard_count:
            raise ValueError("shard_index must be within shard_count")
        return self


class MusicBrainzCollectionResult(BaseModel):
    """Summary of a resumable MusicBrainz collection invocation."""

    model_config = ConfigDict(frozen=True)

    event: str = "musicbrainz_collection_complete"
    mode: str
    run_key: str
    phase: str
    start_date: date
    end_date: date
    shard_count: int
    shard_index: int | None
    release_groups_seen: int


def incremental_window(as_of: date) -> tuple[date, date]:
    """Return the inclusive trailing 14-day window ending at ``as_of``."""
    return as_of - timedelta(days=13), as_of


def build_release_group_query(
    start_date: date,
    end_date: date,
    genres: Sequence[str],
) -> str:
    """Build the date-window and configured-tag Lucene query."""
    if start_date > end_date:
        msg = "start_date must not be after end_date"
        raise ValueError(msg)
    if not genres:
        msg = "at least one genre is required"
        raise ValueError(msg)
    tag_clauses = " OR ".join(f'tag:"{_escape_lucene(genre)}"' for genre in genres)
    return (
        f"firstreleasedate:[{start_date.isoformat()} TO {end_date.isoformat()}] "
        f"AND ({tag_clauses})"
    )


async def collect_release_groups(
    genres: Sequence[str],
    start_date: date,
    end_date: date,
    client: MusicBrainzClient,
    writer: MusicBrainzReleaseGroupWriter,
    *,
    fetched_at: datetime | None = None,
) -> int:
    """Page through a date window and insert each MBID at most once."""
    await writer.initialize()
    query = build_release_group_query(start_date, end_date, genres)
    snapshot_time = fetched_at or datetime.now(UTC)
    offset = 0
    release_groups: dict[str, RawMusicBrainzReleaseGroup] = {}

    while True:
        payload = await client.get(
            "release-group",
            {
                "query": query,
                "inc": RELEASE_GROUP_INCLUDES,
                "limit": RELEASE_GROUP_PAGE_SIZE,
                "offset": offset,
            },
        )
        page = ReleaseGroupSearchResponse.model_validate(payload)
        for release_group in page.release_groups:
            types = tuple(
                value
                for value in (release_group.primary_type, *release_group.secondary_types)
                if value is not None
            )
            artist_credits = tuple(
                ArtistCreditRecord(
                    credit_name=credit.name,
                    artist_name=credit.artist.name,
                    mbid=credit.artist.id,
                    join_phrase=credit.join_phrase,
                )
                for credit in release_group.artist_credit
            )
            release_groups.setdefault(
                release_group.id,
                RawMusicBrainzReleaseGroup(
                    release_group_mbid=release_group.id,
                    title=release_group.title,
                    artist_credits=artist_credits,
                    artist_mbids=tuple(
                        dict.fromkeys(credit.mbid for credit in artist_credits)
                    ),
                    first_release_date=release_group.first_release_date,
                    types=types,
                    genres=tuple(genre.name for genre in release_group.genres),
                    tags=tuple(
                        TagCountRecord(name=tag.name, count=tag.count)
                        for tag in release_group.tags
                    ),
                    fetched_at=snapshot_time,
                ),
            )

        received = len(page.release_groups)
        offset += received
        if received == 0 or offset >= page.count:
            break

    return await writer.insert_first_sight(tuple(release_groups.values()))


def _escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"invalid ISO date: {value}"
        raise argparse.ArgumentTypeError(msg) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument("--genres", type=Path, default=DEFAULT_GENRES_PATH)
    parser.add_argument("--cache", type=Path, default=Path(".cache/musicbrainz"))
    parser.add_argument(
        "--scaling-config",
        type=Path,
        default=DEFAULT_SCALING_CONFIG_PATH,
    )
    parser.add_argument("--run-key")
    parser.add_argument(
        "--phase",
        choices=("all", "collect", "finalize"),
        default="all",
    )
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    incremental = subparsers.add_parser("incremental", help="collect trailing 14 days")
    incremental.add_argument("--as-of", type=_iso_date, default=datetime.now(UTC).date())

    backfill = subparsers.add_parser("backfill", help="collect an arbitrary date range")
    backfill.add_argument("--start", type=_iso_date, required=True)
    backfill.add_argument("--end", type=_iso_date, required=True)
    return parser


def _settings_from_args(args: argparse.Namespace) -> MusicBrainzCollectSettings:
    if args.mode == "incremental":
        start_date, end_date = incremental_window(args.as_of)
    else:
        start_date, end_date = args.start, args.end
    run_key = args.run_key or (
        f"musicbrainz-{start_date.isoformat()}-{end_date.isoformat()}"
    )
    return MusicBrainzCollectSettings(
        mode=args.mode,
        start_date=start_date,
        end_date=end_date,
        database_path=args.database,
        genres_path=args.genres,
        cache_directory=args.cache,
        scaling_config_path=args.scaling_config,
        run_key=run_key,
        phase=args.phase,
        shard_count=args.shard_count,
        shard_index=args.shard_index,
    )


async def async_main(
    settings: MusicBrainzCollectSettings,
) -> MusicBrainzCollectionResult:
    """Run or resume one configured supply collection."""

    genres = load_genres(settings.genres_path, source="musicbrainz").genres
    taxonomy = load_taxonomy(settings.genres_path)
    scaling = load_scaling_config(settings.scaling_config_path)
    if taxonomy.taxonomy_version != scaling.taxonomy_version:
        raise ValueError("collection scaling and taxonomy versions must match")
    writer = MusicBrainzReleaseGroupWriter(settings.database_path)
    checkpoints = CollectionCheckpointStore(settings.database_path)
    await writer.initialize()
    await checkpoints.initialize()
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "source": "musicbrainz",
                "taxonomy_version": taxonomy.taxonomy_version,
                "tags": genres,
                "start_date": settings.start_date.isoformat(),
                "end_date": settings.end_date.isoformat(),
                "shard_count": settings.shard_count,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = await checkpoints.get(
        "musicbrainz",
        settings.run_key,
        "run",
        "metadata",
    )
    snapshot_at = (
        CollectionRunMetadata.model_validate_json(existing.payload_json).snapshot_at
        if existing is not None
        else datetime.now(UTC)
    )
    metadata = CollectionRunMetadata(
        taxonomy_version=taxonomy.taxonomy_version,
        shard_count=settings.shard_count,
        snapshot_at=snapshot_at,
        plan_fingerprint=fingerprint,
    )
    await checkpoints.ensure_run("musicbrainz", settings.run_key, metadata)
    cache = DiskJsonCache(
        settings.cache_directory,
        max_age_seconds=MUSICBRAINZ_CACHE_MAX_AGE_SECONDS,
    )
    seen_count = 0
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = MusicBrainzClient(
            http_client,
            cache=cache,
            user_agent=musicbrainz_user_agent(),
        )
        if settings.phase == "all":
            for shard_index in range(settings.shard_count):
                seen_count += await collect_musicbrainz_shard(
                    genres,
                    settings.start_date,
                    settings.end_date,
                    client,
                    writer,
                    checkpoints,
                    run_key=settings.run_key,
                    metadata=metadata,
                    shard_index=shard_index,
                    max_tags_per_query=scaling.musicbrainz.max_tags_per_query,
                )
            seen_count = await finalize_musicbrainz_run(
                checkpoints,
                run_key=settings.run_key,
                metadata=metadata,
            )
        elif settings.phase == "collect":
            seen_count = await collect_musicbrainz_shard(
                genres,
                settings.start_date,
                settings.end_date,
                client,
                writer,
                checkpoints,
                run_key=settings.run_key,
                metadata=metadata,
                shard_index=settings.shard_index,
                max_tags_per_query=scaling.musicbrainz.max_tags_per_query,
            )
        else:
            seen_count = await finalize_musicbrainz_run(
                checkpoints,
                run_key=settings.run_key,
                metadata=metadata,
            )
    return MusicBrainzCollectionResult(
        mode=settings.mode,
        run_key=settings.run_key,
        phase=settings.phase,
        start_date=settings.start_date,
        end_date=settings.end_date,
        shard_count=settings.shard_count,
        shard_index=None if settings.phase in {"all", "finalize"} else settings.shard_index,
        release_groups_seen=seen_count,
    )


def main() -> None:
    """CLI entrypoint."""
    settings = _settings_from_args(_build_parser().parse_args())
    result = asyncio.run(async_main(settings))
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
