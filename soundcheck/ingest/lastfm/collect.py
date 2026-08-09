"""Collect cumulative Last.fm snapshots; the first run produces no metrics.

Last.fm values are lifetime totals, not events. This module only appends raw
observations keyed by ``fetched_at``. Downstream listening metrics must be
deltas between later snapshots, must exclude each entity's first observation,
and must never zero-fill it. Future sessions must not "fix" the correct
first-run behavior by treating initial totals as weekly activity.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from soundcheck.config import DEFAULT_GENRES_PATH, load_genres
from soundcheck.ingest.checkpoints import (
    CollectionCheckpointStore,
    CollectionRunMetadata,
)
from soundcheck.ingest.http import QueryValue
from soundcheck.ingest.lastfm.client import LastfmApiError, LastfmClient
from soundcheck.ingest.lastfm.models import (
    ArtistGetInfoResponse,
    LastfmArtistSnapshot,
    LastfmTagSnapshot,
    RankedAlbum,
    RankedArtist,
    TagGetInfoResponse,
    TagGetTopAlbumsResponse,
    TagGetTopArtistsResponse,
)
from soundcheck.ingest.lastfm.resumable import (
    collect_artist_shard,
    collect_tag_shard,
    finalize_lastfm_run,
)
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.ingest.scaling import (
    DEFAULT_SCALING_CONFIG_PATH,
    load_scaling_config,
)
from soundcheck.taxonomy import load_taxonomy


class LastfmCollectSettings(BaseModel):
    """Validated collection CLI settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    genres_path: Path = DEFAULT_GENRES_PATH
    cache_directory: Path = Path(".cache/lastfm")
    scaling_config_path: Path = DEFAULT_SCALING_CONFIG_PATH
    run_key: str
    phase: Literal["all", "tags", "artists", "finalize"] = "all"
    shard_count: int = 1
    shard_index: int = 0


class LastfmCollectionResult(BaseModel):
    """Summary of checkpoint work and finalized append-only rows."""

    model_config = ConfigDict(frozen=True)

    event: str = "lastfm_collection_complete"
    run_key: str
    phase: str
    shard_count: int
    shard_index: int | None
    checkpoint_units_written: int
    tag_snapshots: int | None
    artist_snapshots: int | None


@dataclass(slots=True)
class _ArtistReference:
    name: str
    mbid: str | None
    source_genres: set[str] = field(default_factory=set)


def weekly_run_key(as_of: datetime) -> str:
    """Return one stable Last.fm checkpoint key per UTC ISO week."""

    iso = as_of.astimezone(UTC).date().isocalendar()
    return f"lastfm-{iso.year}-W{iso.week:02d}"


async def collect_lastfm(
    genres: Sequence[str],
    client: LastfmClient,
    writer: LastfmSnapshotWriter,
    *,
    fetched_at: datetime | None = None,
    artist_concurrency: int = 8,
    logger: logging.Logger | None = None,
) -> tuple[int, int]:
    """Collect one append-only snapshot run for the configured genre universe."""
    if artist_concurrency <= 0:
        msg = "artist_concurrency must be positive"
        raise ValueError(msg)
    await writer.initialize()
    snapshot_time = fetched_at or datetime.now(UTC)
    tag_snapshots: list[LastfmTagSnapshot] = []
    artist_references: dict[str, _ArtistReference] = {}

    for genre_number, genre in enumerate(genres, start=1):
        info_payload, artists_payload, albums_payload = await asyncio.gather(
            client.get("tag.getInfo", {"tag": genre}),
            client.get("tag.getTopArtists", {"tag": genre, "limit": 100}),
            client.get("tag.getTopAlbums", {"tag": genre, "limit": 50}),
        )
        info = TagGetInfoResponse.model_validate(info_payload).tag
        artists = TagGetTopArtistsResponse.model_validate(
            artists_payload
        ).topartists.artist[:100]
        albums = TagGetTopAlbumsResponse.model_validate(albums_payload).topalbums.album[:50]

        ranked_artists = tuple(
            RankedArtist(
                name=artist.name,
                mbid=artist.mbid,
                rank=artist.rank_attributes.rank,
            )
            for artist in artists
        )
        ranked_albums = tuple(
            RankedAlbum(
                title=album.name,
                mbid=album.mbid,
                artist_name=album.artist.name,
                artist_mbid=album.artist.mbid,
                rank=album.rank_attributes.rank,
            )
            for album in albums
        )
        tag_snapshots.append(
            LastfmTagSnapshot(
                tag=genre,
                reach=info.reach,
                total=info.total,
                top_artists=ranked_artists,
                top_albums=ranked_albums,
                fetched_at=snapshot_time,
            )
        )
        for artist in ranked_artists:
            _remember_artist(artist_references, artist.name, artist.mbid, genre)
        for album in ranked_albums:
            _remember_artist(
                artist_references,
                album.artist_name,
                album.artist_mbid,
                genre,
            )
        _log_progress(
            logger,
            "lastfm_genre_progress",
            genre=genre,
            genres_completed=genre_number,
            genres_total=len(genres),
            artists_discovered=len(artist_references),
        )

    semaphore = asyncio.Semaphore(artist_concurrency)
    artist_total = len(artist_references)
    artist_completed = 0
    artists_skipped = 0
    _log_progress(
        logger,
        "lastfm_artist_phase_started",
        artists_completed=artist_completed,
        artists_total=artist_total,
    )

    async def fetch_artist(
        reference: _ArtistReference,
    ) -> LastfmArtistSnapshot | None:
        nonlocal artist_completed, artists_skipped
        params: dict[str, QueryValue]
        if reference.mbid is not None:
            params = {"mbid": reference.mbid}
        else:
            params = {"artist": reference.name, "autocorrect": 1}
        async with semaphore:
            try:
                payload = await client.get("artist.getInfo", params)
            except LastfmApiError as error:
                if error.code != 6:
                    raise
                if reference.mbid is None:
                    payload = None
                else:
                    _log_progress(
                        logger,
                        "lastfm_artist_name_fallback",
                        artist_name=reference.name,
                        error_code=error.code,
                    )
                    try:
                        payload = await client.get(
                            "artist.getInfo",
                            {"artist": reference.name, "autocorrect": 1},
                        )
                    except LastfmApiError as fallback_error:
                        if fallback_error.code != 6:
                            raise
                        payload = None
        if payload is None:
            artist_completed += 1
            artists_skipped += 1
            _log_progress(
                logger,
                "lastfm_artist_skipped",
                artist_name=reference.name,
                error_code=6,
                lookup_type="mbid_then_name"
                if reference.mbid is not None
                else "name",
            )
            _log_artist_progress(
                logger,
                artist_completed=artist_completed,
                artist_total=artist_total,
                artists_skipped=artists_skipped,
            )
            return None
        artist = ArtistGetInfoResponse.model_validate(payload).artist
        snapshot = LastfmArtistSnapshot(
            artist_name=artist.name,
            mbid=artist.mbid,
            listeners=artist.stats.listeners,
            playcount=artist.stats.playcount,
            tags=tuple(tag.name for tag in artist.tags.tag),
            source_genres=tuple(sorted(reference.source_genres)),
            fetched_at=snapshot_time,
        )
        artist_completed += 1
        _log_artist_progress(
            logger,
            artist_completed=artist_completed,
            artist_total=artist_total,
            artists_skipped=artists_skipped,
        )
        return snapshot

    artist_results = await asyncio.gather(
        *(fetch_artist(reference) for reference in artist_references.values())
    )
    artist_snapshots = [
        snapshot for snapshot in artist_results if snapshot is not None
    ]
    _log_progress(
        logger,
        "lastfm_artist_phase_complete",
        artists_completed=artist_completed,
        artists_total=artist_total,
        artist_snapshots_ready=len(artist_snapshots),
        artists_skipped=artists_skipped,
    )
    return await writer.append(tag_snapshots, artist_snapshots)


def _log_artist_progress(
    logger: logging.Logger | None,
    *,
    artist_completed: int,
    artist_total: int,
    artists_skipped: int,
) -> None:
    if artist_completed % 25 != 0 and artist_completed != artist_total:
        return
    _log_progress(
        logger,
        "lastfm_artist_progress",
        artists_completed=artist_completed,
        artists_total=artist_total,
        artist_snapshots_ready=artist_completed - artists_skipped,
        artists_skipped=artists_skipped,
    )


def _log_progress(
    logger: logging.Logger | None,
    event: str,
    **fields: str | int,
) -> None:
    if logger is None:
        return
    logger.info(
        json.dumps(
            {"event": event, **fields},
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _remember_artist(
    references: dict[str, _ArtistReference],
    name: str,
    mbid: str | None,
    genre: str,
) -> None:
    key = f"mbid:{mbid}" if mbid is not None else f"name:{name.casefold()}"
    reference = references.setdefault(key, _ArtistReference(name=name, mbid=mbid))
    reference.source_genres.add(genre)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument("--genres", type=Path, default=DEFAULT_GENRES_PATH)
    parser.add_argument("--cache", type=Path, default=Path(".cache/lastfm"))
    parser.add_argument(
        "--scaling-config",
        type=Path,
        default=DEFAULT_SCALING_CONFIG_PATH,
    )
    parser.add_argument("--run-key")
    parser.add_argument(
        "--phase",
        choices=("all", "tags", "artists", "finalize"),
        default="all",
    )
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    return parser


async def async_main(settings: LastfmCollectSettings) -> LastfmCollectionResult:
    """Run or resume one Last.fm snapshot collection."""

    if settings.shard_count <= 0:
        raise ValueError("shard_count must be positive")
    if settings.shard_index < 0 or settings.shard_index >= settings.shard_count:
        raise ValueError("shard_index must be within shard_count")
    genres = load_genres(settings.genres_path, source="lastfm").genres
    taxonomy = load_taxonomy(settings.genres_path)
    scaling = load_scaling_config(settings.scaling_config_path)
    if taxonomy.taxonomy_version != scaling.taxonomy_version:
        raise ValueError("collection scaling and taxonomy versions must match")
    writer = LastfmSnapshotWriter(settings.database_path)
    checkpoints = CollectionCheckpointStore(settings.database_path)
    await checkpoints.initialize()
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "source": "lastfm",
                "taxonomy_version": taxonomy.taxonomy_version,
                "tags": genres,
                "shard_count": settings.shard_count,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = await checkpoints.get(
        "lastfm",
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
    await checkpoints.ensure_run("lastfm", settings.run_key, metadata)
    checkpoint_units = 0
    tag_count: int | None = None
    artist_count: int | None = None
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = LastfmClient.from_env(
            http_client,
            cache_directory=settings.cache_directory,
        )
        if settings.phase == "all":
            for shard_index in range(settings.shard_count):
                checkpoint_units += await collect_tag_shard(
                    genres,
                    client,
                    checkpoints,
                    run_key=settings.run_key,
                    metadata=metadata,
                    shard_index=shard_index,
                )
            for shard_index in range(settings.shard_count):
                checkpoint_units += await collect_artist_shard(
                    genres,
                    client,
                    checkpoints,
                    run_key=settings.run_key,
                    metadata=metadata,
                    shard_index=shard_index,
                    concurrency=scaling.lastfm.artist_concurrency,
                )
            tag_count, artist_count = await finalize_lastfm_run(
                genres,
                checkpoints,
                writer,
                run_key=settings.run_key,
                metadata=metadata,
            )
        elif settings.phase == "tags":
            checkpoint_units = await collect_tag_shard(
                genres,
                client,
                checkpoints,
                run_key=settings.run_key,
                metadata=metadata,
                shard_index=settings.shard_index,
            )
        elif settings.phase == "artists":
            checkpoint_units = await collect_artist_shard(
                genres,
                client,
                checkpoints,
                run_key=settings.run_key,
                metadata=metadata,
                shard_index=settings.shard_index,
                concurrency=scaling.lastfm.artist_concurrency,
            )
        else:
            tag_count, artist_count = await finalize_lastfm_run(
                genres,
                checkpoints,
                writer,
                run_key=settings.run_key,
                metadata=metadata,
            )
    return LastfmCollectionResult(
        run_key=settings.run_key,
        phase=settings.phase,
        shard_count=settings.shard_count,
        shard_index=None if settings.phase in {"all", "finalize"} else settings.shard_index,
        checkpoint_units_written=checkpoint_units,
        tag_snapshots=tag_count,
        artist_snapshots=artist_count,
    )


def _configure_cli_logger() -> None:
    """Enable progress logs without enabling httpx logs that contain the API key."""
    logger = logging.getLogger("soundcheck.ingest.lastfm.collect")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def main() -> None:
    """CLI entrypoint."""
    _configure_cli_logger()
    args = _build_parser().parse_args()
    settings = LastfmCollectSettings(
        database_path=args.database,
        genres_path=args.genres,
        cache_directory=args.cache,
        scaling_config_path=args.scaling_config,
        run_key=args.run_key or weekly_run_key(datetime.now(UTC)),
        phase=args.phase,
        shard_count=args.shard_count,
        shard_index=args.shard_index,
    )
    try:
        result = asyncio.run(async_main(settings))
    except KeyboardInterrupt:
        print(
            json.dumps(
                {
                    "event": "lastfm_collection_interrupted",
                    "cached_responses_retained": True,
                    "snapshot_write_is_atomic": True,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        raise SystemExit(130) from None
    print(result.model_dump_json())


if __name__ == "__main__":
    main()
