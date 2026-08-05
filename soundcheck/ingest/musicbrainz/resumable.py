"""Sequential, page-resumable MusicBrainz release-group collection."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from soundcheck.ingest.checkpoints import (
    CollectionCheckpointStore,
    CollectionRunMetadata,
)
from soundcheck.ingest.musicbrainz.client import MusicBrainzClient
from soundcheck.ingest.musicbrainz.models import (
    ArtistCreditRecord,
    RawMusicBrainzReleaseGroup,
    ReleaseGroupSearchResponse,
    TagCountRecord,
)
from soundcheck.ingest.musicbrainz.storage import MusicBrainzReleaseGroupWriter
from soundcheck.ingest.scaling import deterministic_shard

RELEASE_GROUP_PAGE_SIZE = 100
RELEASE_GROUP_INCLUDES = "genres+tags+artist-credits"
PAGE_PHASE = "musicbrainz_page"
SHARD_PHASE = "musicbrainz_shard"


class MusicBrainzPageCheckpoint(BaseModel):
    """One immutable API page and its parsed release-group evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_index: int = Field(ge=0)
    offset: int = Field(ge=0)
    total_count: int = Field(ge=0)
    received: int = Field(ge=0)
    release_groups: tuple[RawMusicBrainzReleaseGroup, ...]


class MusicBrainzShardCheckpoint(BaseModel):
    """Terminal record proving one external shard was inserted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shard_index: int = Field(ge=0)
    query_count: int = Field(ge=0)
    release_groups_seen: int = Field(ge=0)


async def collect_musicbrainz_shard(
    genres: Sequence[str],
    start_date: date,
    end_date: date,
    client: MusicBrainzClient,
    writer: MusicBrainzReleaseGroupWriter,
    checkpoints: CollectionCheckpointStore,
    *,
    run_key: str,
    metadata: CollectionRunMetadata,
    shard_index: int,
    max_tags_per_query: int,
) -> int:
    """Collect one deterministic tag shard, resuming at the first absent page."""

    if max_tags_per_query <= 0:
        raise ValueError("max_tags_per_query must be positive")
    await writer.initialize()
    await checkpoints.ensure_run("musicbrainz", run_key, metadata)
    completed = await checkpoints.get(
        "musicbrainz",
        run_key,
        SHARD_PHASE,
        str(shard_index),
    )
    if completed is not None:
        return MusicBrainzShardCheckpoint.model_validate_json(
            completed.payload_json
        ).release_groups_seen

    shard_tags = deterministic_shard(
        tuple(genres),
        shard_count=metadata.shard_count,
        shard_index=shard_index,
        key=str.casefold,
    )
    query_chunks = tuple(
        shard_tags[index : index + max_tags_per_query]
        for index in range(0, len(shard_tags), max_tags_per_query)
    )
    releases: dict[str, RawMusicBrainzReleaseGroup] = {}
    for query_index, query_tags in enumerate(query_chunks):
        query = build_release_group_query(start_date, end_date, query_tags)
        offset = 0
        while True:
            unit_key = f"{shard_index}:{query_index}:{offset}"
            saved = await checkpoints.get(
                "musicbrainz",
                run_key,
                PAGE_PHASE,
                unit_key,
            )
            if saved is None:
                payload = await client.get(
                    "release-group",
                    {
                        "query": query,
                        "inc": RELEASE_GROUP_INCLUDES,
                        "limit": RELEASE_GROUP_PAGE_SIZE,
                        "offset": offset,
                    },
                )
                page = _parse_page(payload, query_index, metadata)
                await checkpoints.put(
                    "musicbrainz",
                    run_key,
                    PAGE_PHASE,
                    unit_key,
                    shard_index=shard_index,
                    payload_json=page.model_dump_json(),
                )
            else:
                page = MusicBrainzPageCheckpoint.model_validate_json(
                    saved.payload_json
                )
            for release_group in page.release_groups:
                releases.setdefault(release_group.release_group_mbid, release_group)
            offset += page.received
            if page.received == 0 or offset >= page.total_count:
                break

    await writer.insert_first_sight(tuple(releases.values()))
    summary = MusicBrainzShardCheckpoint(
        shard_index=shard_index,
        query_count=len(query_chunks),
        release_groups_seen=len(releases),
    )
    await checkpoints.put(
        "musicbrainz",
        run_key,
        SHARD_PHASE,
        str(shard_index),
        shard_index=shard_index,
        payload_json=summary.model_dump_json(),
    )
    return len(releases)


async def finalize_musicbrainz_run(
    checkpoints: CollectionCheckpointStore,
    *,
    run_key: str,
    metadata: CollectionRunMetadata,
) -> int:
    """Mark the run complete only after every deterministic shard is present."""

    await checkpoints.ensure_run("musicbrainz", run_key, metadata)
    records = await checkpoints.phase("musicbrainz", run_key, SHARD_PHASE)
    by_index = {
        checkpoint.shard_index: checkpoint
        for checkpoint in (
            MusicBrainzShardCheckpoint.model_validate_json(record.payload_json)
            for record in records
        )
    }
    missing = sorted(set(range(metadata.shard_count)) - by_index.keys())
    if missing:
        raise RuntimeError(
            f"MusicBrainz collection is incomplete; missing shards {missing}"
        )
    total = sum(checkpoint.release_groups_seen for checkpoint in by_index.values())
    await checkpoints.mark_completed(
        "musicbrainz",
        run_key,
        payload_json=json.dumps(
            {"release_groups_seen": total},
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    return total


def build_release_group_query(
    start_date: date,
    end_date: date,
    genres: Sequence[str],
) -> str:
    """Build a bounded official MusicBrainz Lucene query."""

    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    if not genres:
        raise ValueError("at least one genre is required")
    tag_clauses = " OR ".join(
        f'tag:"{_escape_lucene(genre)}"' for genre in genres
    )
    return (
        f"firstreleasedate:[{start_date.isoformat()} TO {end_date.isoformat()}] "
        f"AND ({tag_clauses})"
    )


def _escape_lucene(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _parse_page(
    payload: object,
    query_index: int,
    metadata: CollectionRunMetadata,
) -> MusicBrainzPageCheckpoint:
    page = ReleaseGroupSearchResponse.model_validate(payload)
    release_groups = []
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
        release_groups.append(
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
                fetched_at=metadata.snapshot_at,
            )
        )
    return MusicBrainzPageCheckpoint(
        query_index=query_index,
        offset=page.offset,
        total_count=page.count,
        received=len(page.release_groups),
        release_groups=tuple(release_groups),
    )
