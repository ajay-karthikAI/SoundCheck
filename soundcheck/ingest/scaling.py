"""Deterministic collection planning, artist deduplication, and sharding."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from soundcheck.ingest.musicbrainz.windows import incremental_window
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy, normalize_alias

DEFAULT_SCALING_CONFIG_PATH = Path("config/collection_scaling.yml")


class LastfmScalingConfig(BaseModel):
    """Fixed Last.fm safety assumptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requests_per_second: float
    tag_methods_per_tag: Literal[3]
    expected_artists_per_unobserved_tag: int = Field(ge=1, le=150)
    cache_hit_assumption: float = Field(ge=0.0, le=1.0)
    artist_concurrency: int = Field(ge=1, le=32)

    @field_validator("requests_per_second")
    @classmethod
    def preserve_lastfm_limit(cls, value: float) -> float:
        if value != 4.0:
            raise ValueError("Last.fm must remain limited to 4 requests/second")
        return value


class MusicBrainzScalingConfig(BaseModel):
    """Fixed MusicBrainz safety assumptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requests_per_second: float
    page_size: Literal[100]
    max_tags_per_query: int = Field(ge=1, le=50)
    expected_pages_per_query: int = Field(ge=1, le=100)
    cache_hit_assumption: float = Field(ge=0.0, le=1.0)
    incremental_days: Literal[14]

    @field_validator("requests_per_second")
    @classmethod
    def preserve_musicbrainz_limit(cls, value: float) -> float:
        if value != 1.0:
            raise ValueError("MusicBrainz must remain limited to 1 request/second")
        return value


class CollectionScalingConfig(BaseModel):
    """Validated runtime and sharding configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    safe_window_seconds: int = Field(ge=60)
    max_shards: int = Field(ge=1, le=64)
    lastfm: LastfmScalingConfig
    musicbrainz: MusicBrainzScalingConfig


def load_scaling_config(path: Path = DEFAULT_SCALING_CONFIG_PATH) -> CollectionScalingConfig:
    """Load collection scaling configuration."""

    return CollectionScalingConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


class ArtistCandidate(BaseModel):
    """One artist reference discovered under a source genre tag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    mbid: str | None = None
    source_genre: str

    @field_validator("mbid", mode="before")
    @classmethod
    def blank_mbid_is_missing(cls, value: object) -> object:
        return None if value == "" else value


class DeduplicatedArtist(BaseModel):
    """One global MBID-first artist request with all source genres retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_key: str
    name: str
    mbid: str | None
    source_genres: tuple[str, ...]


def deduplicate_artist_candidates(
    candidates: Iterable[ArtistCandidate],
) -> tuple[DeduplicatedArtist, ...]:
    """Deduplicate globally, preferring a unique MBID observed for a name."""

    materialized = tuple(candidates)
    name_mbids: dict[str, set[str]] = defaultdict(set)
    for candidate in materialized:
        if candidate.mbid:
            name_mbids[normalize_alias(candidate.name)].add(candidate.mbid.casefold())
    unique_name_mbid = {
        name: next(iter(mbids))
        for name, mbids in name_mbids.items()
        if len(mbids) == 1
    }
    grouped: dict[str, list[ArtistCandidate]] = defaultdict(list)
    for candidate in materialized:
        normalized_name = normalize_alias(candidate.name)
        mbid = candidate.mbid.casefold() if candidate.mbid else unique_name_mbid.get(
            normalized_name
        )
        key = f"mbid:{mbid}" if mbid else f"name:{normalized_name}"
        grouped[key].append(candidate)

    artists = []
    for key, references in sorted(grouped.items()):
        explicit_mbids = sorted(
            {
                reference.mbid
                for reference in references
                if reference.mbid is not None
            },
            key=str.casefold,
        )
        names = sorted(
            {reference.name for reference in references},
            key=lambda value: (value.casefold(), value),
        )
        artists.append(
            DeduplicatedArtist(
                request_key=key,
                name=names[0],
                mbid=explicit_mbids[0] if explicit_mbids else None,
                source_genres=tuple(
                    sorted(
                        {reference.source_genre for reference in references},
                        key=str.casefold,
                    )
                ),
            )
        )
    return tuple(artists)


def shard_for_key(key: str, shard_count: int) -> int:
    """Assign a stable key to one deterministic shard."""

    if shard_count <= 0:
        raise ValueError("shard_count must be positive")
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % shard_count


def deterministic_shard[Item](
    items: Sequence[Item],
    *,
    shard_count: int,
    shard_index: int,
    key: Callable[[Item], str],
) -> tuple[Item, ...]:
    """Return one stable shard, sorted by its deterministic key."""

    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard_index must be within shard_count")
    return tuple(
        sorted(
            (
                item
                for item in items
                if shard_for_key(key(item), shard_count) == shard_index
            ),
            key=key,
        )
    )


class SourceCollectionPlan(BaseModel):
    """Dry-run request and runtime plan for one official source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["lastfm", "musicbrainz"]
    tags: tuple[str, ...]
    tag_count: int
    observed_tag_count: int | None
    unobserved_tag_count: int | None
    tag_requests: int | None
    observed_deduplicated_artist_count: int | None
    expected_deduplicated_artist_count: int | None
    expected_artist_requests: int | None
    expected_pages: int | None
    expected_requests_before_cache: int
    cache_hit_assumption: float
    expected_uncached_requests: int
    requests_per_second: float
    estimated_runtime_seconds: float
    shard_count: int
    estimated_seconds_per_shard: float
    safe_window_seconds: int
    within_safe_window_per_shard: bool


class CollectionPlan(BaseModel):
    """Combined taxonomy-v2 dry-run collection plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["collection_dry_run_plan"] = "collection_dry_run_plan"
    taxonomy_version: str
    generated_at: datetime
    incremental_start_date: date
    incremental_end_date: date
    lastfm: SourceCollectionPlan
    musicbrainz: SourceCollectionPlan

    _generated_at_utc = field_validator("generated_at")(
        lambda value: value.astimezone(UTC)
    )


def _planner_evidence(
    database_path: Path,
    *,
    start_date: date,
    end_date: date,
) -> tuple[tuple[ArtistCandidate, ...], set[str], int]:
    if not database_path.exists():
        return (), set(), 0
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_planner_lastfm_artist_refs.sql")
            ).fetchall()
            mb_count = connection.execute(
                load_sql("count_planner_mb_window.sql"),
                [start_date, end_date],
            ).fetchone()
    except duckdb.CatalogException:
        return (), set(), 0
    candidates: list[ArtistCandidate] = []
    observed_tags: set[str] = set()
    for tag, top_artists, top_albums, _fetched_at in rows:
        observed_tags.add(str(tag).casefold())
        for artist in top_artists or ():
            candidates.append(
                ArtistCandidate(
                    name=artist["name"],
                    mbid=artist["mbid"],
                    source_genre=tag,
                )
            )
        for album in top_albums or ():
            candidates.append(
                ArtistCandidate(
                    name=album["artist_name"],
                    mbid=album["artist_mbid"],
                    source_genre=tag,
                )
            )
    return tuple(candidates), observed_tags, int(mb_count[0] if mb_count else 0)


def _shard_count(runtime: float, config: CollectionScalingConfig) -> int:
    required = max(1, math.ceil(runtime / config.safe_window_seconds))
    return min(config.max_shards, required)


def build_collection_plan(
    *,
    database_path: Path,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    config_path: Path = DEFAULT_SCALING_CONFIG_PATH,
    as_of: date,
    generated_at: datetime | None = None,
) -> CollectionPlan:
    """Build a conservative plan without making an API request."""

    taxonomy = load_taxonomy(taxonomy_path)
    config = load_scaling_config(config_path)
    if taxonomy.taxonomy_version != config.taxonomy_version:
        raise ValueError("collection scaling and taxonomy versions must match")
    start_date, end_date = incremental_window(
        as_of,
        days=config.musicbrainz.incremental_days,
    )
    candidates, observed_tags, recent_release_count = _planner_evidence(
        database_path,
        start_date=start_date,
        end_date=end_date,
    )

    lastfm_tags = taxonomy.collection_tags_v2("lastfm")
    target_tag_keys = {tag.casefold() for tag in lastfm_tags}
    observed_target_tags = observed_tags & target_tag_keys
    observed_artists = deduplicate_artist_candidates(
        candidate
        for candidate in candidates
        if candidate.source_genre.casefold() in target_tag_keys
    )
    unobserved_count = len(lastfm_tags) - len(observed_target_tags)
    expected_artists = len(observed_artists) + (
        unobserved_count * config.lastfm.expected_artists_per_unobserved_tag
    )
    tag_requests = len(lastfm_tags) * config.lastfm.tag_methods_per_tag
    lastfm_before_cache = tag_requests + expected_artists
    lastfm_uncached = math.ceil(
        lastfm_before_cache * (1.0 - config.lastfm.cache_hit_assumption)
    )
    lastfm_runtime = lastfm_uncached / config.lastfm.requests_per_second
    lastfm_shards = _shard_count(lastfm_runtime, config)

    mb_tags = taxonomy.collection_tags_v2("musicbrainz")
    query_count = max(
        1,
        math.ceil(len(mb_tags) / config.musicbrainz.max_tags_per_query),
    )
    evidence_pages = math.ceil(recent_release_count / config.musicbrainz.page_size)
    expected_pages = max(
        query_count * config.musicbrainz.expected_pages_per_query,
        evidence_pages,
    )
    mb_uncached = math.ceil(
        expected_pages * (1.0 - config.musicbrainz.cache_hit_assumption)
    )
    mb_runtime = mb_uncached / config.musicbrainz.requests_per_second
    mb_shards = _shard_count(mb_runtime, config)

    return CollectionPlan(
        taxonomy_version=taxonomy.taxonomy_version,
        generated_at=generated_at or datetime.now(UTC),
        incremental_start_date=start_date,
        incremental_end_date=end_date,
        lastfm=SourceCollectionPlan(
            source="lastfm",
            tags=lastfm_tags,
            tag_count=len(lastfm_tags),
            observed_tag_count=len(observed_target_tags),
            unobserved_tag_count=unobserved_count,
            tag_requests=tag_requests,
            observed_deduplicated_artist_count=len(observed_artists),
            expected_deduplicated_artist_count=expected_artists,
            expected_artist_requests=expected_artists,
            expected_pages=None,
            expected_requests_before_cache=lastfm_before_cache,
            cache_hit_assumption=config.lastfm.cache_hit_assumption,
            expected_uncached_requests=lastfm_uncached,
            requests_per_second=config.lastfm.requests_per_second,
            estimated_runtime_seconds=lastfm_runtime,
            shard_count=lastfm_shards,
            estimated_seconds_per_shard=lastfm_runtime / lastfm_shards,
            safe_window_seconds=config.safe_window_seconds,
            within_safe_window_per_shard=(
                lastfm_runtime / lastfm_shards <= config.safe_window_seconds
            ),
        ),
        musicbrainz=SourceCollectionPlan(
            source="musicbrainz",
            tags=mb_tags,
            tag_count=len(mb_tags),
            observed_tag_count=None,
            unobserved_tag_count=None,
            tag_requests=None,
            observed_deduplicated_artist_count=None,
            expected_deduplicated_artist_count=None,
            expected_artist_requests=None,
            expected_pages=expected_pages,
            expected_requests_before_cache=expected_pages,
            cache_hit_assumption=config.musicbrainz.cache_hit_assumption,
            expected_uncached_requests=mb_uncached,
            requests_per_second=config.musicbrainz.requests_per_second,
            estimated_runtime_seconds=mb_runtime,
            shard_count=mb_shards,
            estimated_seconds_per_shard=mb_runtime / mb_shards,
            safe_window_seconds=config.safe_window_seconds,
            within_safe_window_per_shard=(
                mb_runtime / mb_shards <= config.safe_window_seconds
            ),
        ),
    )


def plan_fingerprint(plan: CollectionPlan) -> str:
    """Hash immutable plan inputs for checkpoint compatibility."""

    payload = plan.model_dump(mode="json", exclude={"generated_at"})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
