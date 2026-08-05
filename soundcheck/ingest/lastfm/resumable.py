"""Resumable, globally deduplicated Last.fm snapshot collection."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.ingest.scaling import (
    ArtistCandidate,
    DeduplicatedArtist,
    deduplicate_artist_candidates,
    deterministic_shard,
)

TAG_PHASE = "lastfm_tag"
ARTIST_PHASE = "lastfm_artist"


class LastfmTagDiscovery(BaseModel):
    """One completed tag snapshot plus its artist references."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot: LastfmTagSnapshot
    artist_candidates: tuple[ArtistCandidate, ...]


class LastfmArtistCheckpoint(BaseModel):
    """One completed artist request, including deliberate not-found skips."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_key: str
    status: Literal["ready", "not_found"]
    snapshot: LastfmArtistSnapshot | None

    @model_validator(mode="after")
    def validate_status(self) -> LastfmArtistCheckpoint:
        if (self.status == "ready") != (self.snapshot is not None):
            raise ValueError("ready artist checkpoints require a snapshot")
        return self


def artist_universe(
    discoveries: Sequence[LastfmTagDiscovery],
) -> tuple[DeduplicatedArtist, ...]:
    """Build the single global artist request universe for all genre tags."""

    return deduplicate_artist_candidates(
        candidate
        for discovery in discoveries
        for candidate in discovery.artist_candidates
    )


async def collect_tag_shard(
    genres: Sequence[str],
    client: LastfmClient,
    checkpoints: CollectionCheckpointStore,
    *,
    run_key: str,
    metadata: CollectionRunMetadata,
    shard_index: int,
) -> int:
    """Discover one deterministic tag shard and checkpoint each completed tag."""

    await checkpoints.ensure_run("lastfm", run_key, metadata)
    shard = deterministic_shard(
        tuple(genres),
        shard_count=metadata.shard_count,
        shard_index=shard_index,
        key=str.casefold,
    )
    completed = {
        record.unit_key
        for record in await checkpoints.phase("lastfm", run_key, TAG_PHASE)
    }
    written = 0
    for genre in shard:
        unit_key = genre.casefold()
        if unit_key in completed:
            continue
        discovery = await _fetch_tag(genre, client, metadata.snapshot_at)
        await checkpoints.put(
            "lastfm",
            run_key,
            TAG_PHASE,
            unit_key,
            shard_index=shard_index,
            payload_json=discovery.model_dump_json(),
        )
        written += 1
    return written


async def load_tag_discoveries(
    genres: Sequence[str],
    checkpoints: CollectionCheckpointStore,
    *,
    run_key: str,
) -> tuple[LastfmTagDiscovery, ...]:
    """Load all tag results, refusing to start artists from partial discovery."""

    records = await checkpoints.phase("lastfm", run_key, TAG_PHASE)
    by_key = {
        record.unit_key: LastfmTagDiscovery.model_validate_json(record.payload_json)
        for record in records
    }
    expected = {genre.casefold() for genre in genres}
    missing = sorted(expected - by_key.keys())
    if missing:
        raise RuntimeError(
            f"tag discovery is incomplete; {len(missing)} tag checkpoints missing"
        )
    return tuple(by_key[key] for key in sorted(expected))


async def collect_artist_shard(
    genres: Sequence[str],
    client: LastfmClient,
    checkpoints: CollectionCheckpointStore,
    *,
    run_key: str,
    metadata: CollectionRunMetadata,
    shard_index: int,
    concurrency: int,
) -> int:
    """Fetch one global artist shard without repeating artists across genres."""

    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    await checkpoints.ensure_run("lastfm", run_key, metadata)
    discoveries = await load_tag_discoveries(
        genres,
        checkpoints,
        run_key=run_key,
    )
    artists = artist_universe(discoveries)
    shard = deterministic_shard(
        artists,
        shard_count=metadata.shard_count,
        shard_index=shard_index,
        key=lambda artist: artist.request_key,
    )
    completed = {
        record.unit_key
        for record in await checkpoints.phase("lastfm", run_key, ARTIST_PHASE)
    }
    pending = tuple(artist for artist in shard if artist.request_key not in completed)
    semaphore = asyncio.Semaphore(concurrency)
    checkpoint_lock = asyncio.Lock()

    async def fetch_and_save(artist: DeduplicatedArtist) -> None:
        async with semaphore:
            result = await _fetch_artist(artist, client, metadata.snapshot_at)
        async with checkpoint_lock:
            await checkpoints.put(
                "lastfm",
                run_key,
                ARTIST_PHASE,
                artist.request_key,
                shard_index=shard_index,
                payload_json=result.model_dump_json(),
            )

    await asyncio.gather(*(fetch_and_save(artist) for artist in pending))
    return len(pending)


async def finalize_lastfm_run(
    genres: Sequence[str],
    checkpoints: CollectionCheckpointStore,
    writer: LastfmSnapshotWriter,
    *,
    run_key: str,
    metadata: CollectionRunMetadata,
) -> tuple[int, int]:
    """Atomically append a complete checkpointed run to immutable raw tables."""

    await checkpoints.ensure_run("lastfm", run_key, metadata)
    discoveries = await load_tag_discoveries(
        genres,
        checkpoints,
        run_key=run_key,
    )
    artists = artist_universe(discoveries)
    records = await checkpoints.phase("lastfm", run_key, ARTIST_PHASE)
    by_key = {
        record.unit_key: LastfmArtistCheckpoint.model_validate_json(
            record.payload_json
        )
        for record in records
    }
    missing = sorted({artist.request_key for artist in artists} - by_key.keys())
    if missing:
        raise RuntimeError(
            f"artist collection is incomplete; {len(missing)} checkpoints missing"
        )
    snapshots = tuple(
        checkpoint.snapshot
        for checkpoint in (by_key[artist.request_key] for artist in artists)
        if checkpoint.snapshot is not None
    )
    await writer.initialize()
    return await writer.append_checkpointed(
        run_key,
        tuple(discovery.snapshot for discovery in discoveries),
        snapshots,
    )


async def _fetch_tag(
    genre: str,
    client: LastfmClient,
    snapshot_at: datetime,
) -> LastfmTagDiscovery:
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
    candidates = tuple(
        ArtistCandidate(
            name=artist.name,
            mbid=artist.mbid,
            source_genre=genre,
        )
        for artist in ranked_artists
    ) + tuple(
        ArtistCandidate(
            name=album.artist_name,
            mbid=album.artist_mbid,
            source_genre=genre,
        )
        for album in ranked_albums
    )
    return LastfmTagDiscovery(
        snapshot=LastfmTagSnapshot(
            tag=genre,
            reach=info.reach,
            total=info.total,
            top_artists=ranked_artists,
            top_albums=ranked_albums,
            fetched_at=snapshot_at,
        ),
        artist_candidates=candidates,
    )


async def _fetch_artist(
    reference: DeduplicatedArtist,
    client: LastfmClient,
    snapshot_at: datetime,
) -> LastfmArtistCheckpoint:
    params: dict[str, QueryValue]
    if reference.mbid is not None:
        params = {"mbid": reference.mbid}
    else:
        params = {"artist": reference.name, "autocorrect": 1}
    try:
        payload = await client.get("artist.getInfo", params)
    except LastfmApiError as error:
        if error.code != 6:
            raise
        if reference.mbid is None:
            payload = None
        else:
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
        return LastfmArtistCheckpoint(
            request_key=reference.request_key,
            status="not_found",
            snapshot=None,
        )
    artist = ArtistGetInfoResponse.model_validate(payload).artist
    return LastfmArtistCheckpoint(
        request_key=reference.request_key,
        status="ready",
        snapshot=LastfmArtistSnapshot(
            artist_name=artist.name,
            mbid=artist.mbid,
            listeners=artist.stats.listeners,
            playcount=artist.stats.playcount,
            tags=tuple(tag.name for tag in artist.tags.tag),
            source_genres=reference.source_genres,
            fetched_at=snapshot_at,
        ),
    )
