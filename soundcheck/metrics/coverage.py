"""Batch-computed source coverage for taxonomy-v2 genres.

Coverage is an evidence audit, not an activity metric. Missing source evidence
remains ``None``; it is never converted to zero. Last.fm history is considered
valid only when two consecutive weekly snapshots exist and cumulative counters
are monotone.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from soundcheck.taxonomy import GenreDefinition, GenreTaxonomy, normalize_alias

EligibilityState = Literal[
    "ready",
    "collecting_history",
    "insufficient_listening",
    "insufficient_conversation",
    "insufficient_supply",
    "insufficient_resolution",
    "unsupported",
]


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_week_start(value: date | datetime) -> date:
    """Return the ISO-week Monday for a date or timestamp."""

    day = value.date() if isinstance(value, datetime) else value
    return day - timedelta(days=day.weekday())


class CoverageThresholds(BaseModel):
    """Conservative evidence thresholds loaded from ``config/coverage.yml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str = Field(min_length=1)
    lookback_weeks: int = Field(ge=1, le=520)
    require_lastfm_tag: bool = True
    min_unique_lastfm_artists: int = Field(ge=1)
    min_artists_with_consecutive_valid_snapshots: int = Field(ge=1)
    min_listening_history_weeks: int = Field(ge=2)
    min_musicbrainz_release_groups: int = Field(ge=1)
    min_resolved_bluesky_posts: int = Field(ge=1)
    min_resolution_attempts: int = Field(ge=1)
    min_resolution_rate: float = Field(ge=0.0, le=1.0)
    min_cross_source_overlap_artists: int = Field(ge=0)
    min_cross_source_overlap_rate: float = Field(ge=0.0, le=1.0)
    max_source_age_days: int = Field(ge=1)


def load_coverage_thresholds(path: Path) -> CoverageThresholds:
    """Load and validate coverage thresholds."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CoverageThresholds.model_validate(payload)


class LastfmTagObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag: str
    fetched_at: datetime

    _utc_fetched_at = field_validator("fetched_at", mode="after")(_ensure_utc)


class LastfmArtistObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artist_name: str
    mbid: str | None = None
    listeners: int = Field(ge=0)
    playcount: int = Field(ge=0)
    tags: tuple[str, ...] = ()
    source_genres: tuple[str, ...] = ()
    fetched_at: datetime

    _utc_fetched_at = field_validator("fetched_at", mode="after")(_ensure_utc)


class CoverageArtistCredit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artist_name: str
    mbid: str | None = None


class MusicBrainzReleaseObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_group_mbid: str
    first_release_date: str
    artist_credits: tuple[CoverageArtistCredit, ...] = ()
    genres: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    fetched_at: datetime

    _utc_fetched_at = field_validator("fetched_at", mode="after")(_ensure_utc)


class BlueskyPostObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uri: str
    created_at: datetime
    ingested_at: datetime

    _utc_created_at = field_validator("created_at", mode="after")(_ensure_utc)
    _utc_ingested_at = field_validator("ingested_at", mode="after")(_ensure_utc)


class PostLinkObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    post_uri: str
    artist_mbid: str | None = None
    artist_name_raw: str
    method: str
    score: float = Field(ge=0.0)
    join_key_type: str
    resolved_at: datetime

    _utc_resolved_at = field_validator("resolved_at", mode="after")(_ensure_utc)


class PostAmbiguityObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    post_uri: str
    top_artist_mbid: str | None = None
    top_artist_name: str
    resolved_at: datetime

    _utc_resolved_at = field_validator("resolved_at", mode="after")(_ensure_utc)


class CoverageEvidence(BaseModel):
    """Validated raw evidence read from DuckDB."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lastfm_tags: tuple[LastfmTagObservation, ...] = ()
    lastfm_artists: tuple[LastfmArtistObservation, ...] = ()
    musicbrainz_releases: tuple[MusicBrainzReleaseObservation, ...] = ()
    bluesky_posts: tuple[BlueskyPostObservation, ...] = ()
    post_links: tuple[PostLinkObservation, ...] = ()
    post_ambiguities: tuple[PostAmbiguityObservation, ...] = ()


class GenreCoverageRow(BaseModel):
    """One taxonomy genre's coverage evidence for one ISO week."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    iso_year: int
    iso_week: int = Field(ge=1, le=53)
    genre_id: str
    display_name: str
    slug: str
    macro_family_id: str
    macro_family_name: str
    taxonomy_status: str
    lastfm_tag_available: bool | None
    unique_lastfm_artists: int | None = Field(default=None, ge=1)
    artists_with_consecutive_valid_snapshots: int | None = Field(default=None, ge=1)
    lastfm_history_weeks: int | None = Field(default=None, ge=1)
    musicbrainz_release_group_count: int | None = Field(default=None, ge=1)
    resolved_bluesky_post_count: int | None = Field(default=None, ge=1)
    resolution_attempt_count: int | None = Field(default=None, ge=1)
    resolution_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    cross_source_overlap_artist_count: int | None = Field(default=None, ge=0)
    cross_source_overlap: float | None = Field(default=None, ge=0.0, le=1.0)
    latest_source_timestamp: datetime | None
    listening_missing: bool
    conversation_missing: bool
    supply_missing: bool
    stale: bool
    eligibility_state: EligibilityState
    computed_at: datetime

    _utc_latest = field_validator("latest_source_timestamp", mode="after")(
        lambda value: None if value is None else _ensure_utc(value)
    )
    _utc_computed = field_validator("computed_at", mode="after")(_ensure_utc)

    @model_validator(mode="after")
    def validate_week_and_missingness(self) -> GenreCoverageRow:
        iso = self.week_start.isocalendar()
        if self.week_start.weekday() != 0:
            raise ValueError("week_start must be an ISO-week Monday")
        if (self.iso_year, self.iso_week) != (iso.year, iso.week):
            raise ValueError("iso_year and iso_week must match week_start")
        if self.lastfm_tag_available is False:
            raise ValueError("absent Last.fm evidence must be null, not false")
        if self.listening_missing != (
            self.artists_with_consecutive_valid_snapshots is None
        ):
            raise ValueError("listening_missing must reflect valid snapshot evidence")
        if self.conversation_missing != (self.resolved_bluesky_post_count is None):
            raise ValueError("conversation_missing must reflect resolved-post evidence")
        if self.supply_missing != (self.musicbrainz_release_group_count is None):
            raise ValueError("supply_missing must reflect release evidence")
        return self


class CoverageBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    start_week: date | None
    end_week: date | None
    computed_at: datetime
    rows: tuple[GenreCoverageRow, ...]

    _utc_computed = field_validator("computed_at", mode="after")(_ensure_utc)


@dataclass
class _Cell:
    lastfm_tags: set[str] = field(default_factory=set)
    lastfm_artists: set[str] = field(default_factory=set)
    valid_lastfm_artists: set[str] = field(default_factory=set)
    releases: set[str] = field(default_factory=set)
    resolved_posts: set[str] = field(default_factory=set)
    resolution_attempts: set[str] = field(default_factory=set)
    source_artists: dict[str, set[str]] = field(
        default_factory=lambda: {
            "lastfm": set(),
            "musicbrainz": set(),
            "bluesky": set(),
        }
    )
    timestamps: list[datetime] = field(default_factory=list)


def _source_alias_index(taxonomy: GenreTaxonomy) -> dict[str, str]:
    owners: dict[str, set[str]] = defaultdict(set)
    for genre in taxonomy.genres:
        if genre.status == "rejected" or genre.genre_id in {"other", "unresolved"}:
            continue
        labels = [
            genre.display_name,
            *genre.aliases,
            *(
                alias
                for aliases in genre.multilingual_aliases.values()
                for alias in aliases
            ),
            *genre.lastfm_spelling_variants,
            *genre.musicbrainz_spelling_variants,
        ]
        for label in labels:
            normalized = normalize_alias(label)
            if normalized:
                owners[normalized].add(genre.genre_id)
    return {
        alias: next(iter(genre_ids))
        for alias, genre_ids in owners.items()
        if len(genre_ids) == 1
    }


def _mapped_genres(labels: tuple[str, ...], index: dict[str, str]) -> set[str]:
    return {
        genre_id
        for label in labels
        if (genre_id := index.get(normalize_alias(label))) is not None
    }


def _build_name_mbid_index(evidence: CoverageEvidence) -> dict[str, str]:
    candidates: dict[str, set[str]] = defaultdict(set)

    def add(name: str, mbid: str | None) -> None:
        normalized = normalize_alias(name)
        if normalized and mbid:
            candidates[normalized].add(mbid.casefold())

    for artist in evidence.lastfm_artists:
        add(artist.artist_name, artist.mbid)
    for release in evidence.musicbrainz_releases:
        for credit in release.artist_credits:
            add(credit.artist_name, credit.mbid)
    for link in evidence.post_links:
        add(link.artist_name_raw, link.artist_mbid)
    for ambiguity in evidence.post_ambiguities:
        add(ambiguity.top_artist_name, ambiguity.top_artist_mbid)
    return {
        name: next(iter(mbids))
        for name, mbids in candidates.items()
        if len(mbids) == 1
    }


def _artist_key(
    name: str,
    mbid: str | None,
    name_mbid_index: dict[str, str],
) -> str:
    if mbid:
        return f"mbid:{mbid.casefold()}"
    normalized = normalize_alias(name)
    inferred_mbid = name_mbid_index.get(normalized)
    if inferred_mbid:
        return f"mbid:{inferred_mbid}"
    return f"name:{normalized}"


def _parse_release_date(value: str) -> date | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed


def _week_range(
    observed: set[date],
    lookback_weeks: int,
    start_week: date | None,
    end_week: date | None,
) -> tuple[date, ...]:
    if start_week is not None and start_week.weekday() != 0:
        raise ValueError("start_week must be an ISO-week Monday")
    if end_week is not None and end_week.weekday() != 0:
        raise ValueError("end_week must be an ISO-week Monday")
    if start_week is None and not observed:
        return ()
    resolved_end = end_week or max(observed)
    observed_start = min(observed) if observed else resolved_end
    floor = resolved_end - timedelta(weeks=lookback_weeks - 1)
    resolved_start = start_week or max(observed_start, floor)
    if resolved_start > resolved_end:
        raise ValueError("start_week must not follow end_week")
    count = ((resolved_end - resolved_start).days // 7) + 1
    return tuple(resolved_start + timedelta(weeks=index) for index in range(count))


def _eligibility(
    genre: GenreDefinition,
    cell: _Cell,
    *,
    special_genre_ids: frozenset[str],
    lastfm_tag_available: bool | None,
    unique_lastfm_artists: int | None,
    valid_lastfm_artists: int | None,
    history_weeks: int | None,
    release_count: int | None,
    post_count: int | None,
    resolution_attempts: int | None,
    resolution_rate: float | None,
    overlap_count: int | None,
    overlap_rate: float | None,
    stale: bool,
    thresholds: CoverageThresholds,
) -> EligibilityState:
    has_evidence = bool(
        cell.lastfm_tags
        or cell.lastfm_artists
        or cell.releases
        or cell.resolved_posts
        or cell.resolution_attempts
    )
    if (
        genre.status == "rejected"
        or genre.genre_id in special_genre_ids
        or not has_evidence
        or stale
    ):
        return "unsupported"
    if (
        valid_lastfm_artists is None
        and history_weeks is not None
        and history_weeks < thresholds.min_listening_history_weeks
    ):
        return "collecting_history"
    if (
        (thresholds.require_lastfm_tag and lastfm_tag_available is None)
        or unique_lastfm_artists is None
        or unique_lastfm_artists < thresholds.min_unique_lastfm_artists
        or valid_lastfm_artists is None
        or valid_lastfm_artists
        < thresholds.min_artists_with_consecutive_valid_snapshots
    ):
        return "insufficient_listening"
    if post_count is None or post_count < thresholds.min_resolved_bluesky_posts:
        return "insufficient_conversation"
    if release_count is None or release_count < thresholds.min_musicbrainz_release_groups:
        return "insufficient_supply"
    if (
        resolution_attempts is None
        or resolution_attempts < thresholds.min_resolution_attempts
        or resolution_rate is None
        or resolution_rate < thresholds.min_resolution_rate
        or overlap_count is None
        or overlap_count < thresholds.min_cross_source_overlap_artists
        or overlap_rate is None
        or overlap_rate < thresholds.min_cross_source_overlap_rate
    ):
        return "insufficient_resolution"
    return "ready"


def compute_coverage(
    taxonomy: GenreTaxonomy,
    thresholds: CoverageThresholds,
    evidence: CoverageEvidence,
    *,
    computed_at: datetime,
    start_week: date | None = None,
    end_week: date | None = None,
) -> CoverageBatch:
    """Compute coverage rows without mutating raw evidence or production marts."""

    if taxonomy.taxonomy_version != thresholds.taxonomy_version:
        raise ValueError("coverage and taxonomy versions must match")

    computed_at = _ensure_utc(computed_at)
    alias_index = _source_alias_index(taxonomy)
    name_mbid_index = _build_name_mbid_index(evidence)
    cells: dict[tuple[str, date], _Cell] = defaultdict(_Cell)
    artist_memberships: dict[str, set[str]] = defaultdict(set)
    observed_weeks: set[date] = set()
    history_weeks: dict[str, set[date]] = defaultdict(set)

    for tag in evidence.lastfm_tags:
        week = iso_week_start(tag.fetched_at)
        genre_ids = _mapped_genres((tag.tag,), alias_index)
        observed_weeks.add(week)
        for genre_id in genre_ids:
            cell = cells[(genre_id, week)]
            cell.lastfm_tags.add(normalize_alias(tag.tag))
            cell.timestamps.append(tag.fetched_at)
            history_weeks[genre_id].add(week)

    latest_artist_week: dict[tuple[str, date], LastfmArtistObservation] = {}
    artist_genres: dict[tuple[str, date], set[str]] = {}
    for artist in evidence.lastfm_artists:
        week = iso_week_start(artist.fetched_at)
        key = _artist_key(artist.artist_name, artist.mbid, name_mbid_index)
        genres = _mapped_genres((*artist.tags, *artist.source_genres), alias_index)
        existing = latest_artist_week.get((key, week))
        if existing is None or artist.fetched_at > existing.fetched_at:
            latest_artist_week[(key, week)] = artist
            artist_genres[(key, week)] = genres
        observed_weeks.add(week)

    by_artist: dict[str, list[tuple[date, LastfmArtistObservation]]] = defaultdict(list)
    for (key, week), artist in latest_artist_week.items():
        genres = artist_genres[(key, week)]
        by_artist[key].append((week, artist))
        artist_memberships[key].update(genres)
        name_key = f"name:{normalize_alias(artist.artist_name)}"
        artist_memberships[name_key].update(genres)
        for genre_id in genres:
            cell = cells[(genre_id, week)]
            cell.lastfm_artists.add(key)
            cell.source_artists["lastfm"].add(key)
            cell.timestamps.append(artist.fetched_at)
            history_weeks[genre_id].add(week)

    for key, snapshots in by_artist.items():
        snapshots.sort(key=lambda item: item[0])
        for (previous_week, previous), (week, current) in pairwise(snapshots):
            if (
                week - previous_week != timedelta(weeks=1)
                or current.listeners < previous.listeners
                or current.playcount < previous.playcount
            ):
                continue
            for genre_id in artist_genres[(key, week)]:
                cells[(genre_id, week)].valid_lastfm_artists.add(key)

    for release in evidence.musicbrainz_releases:
        release_date = _parse_release_date(release.first_release_date)
        if release_date is None:
            continue
        week = iso_week_start(release_date)
        genre_ids = _mapped_genres((*release.genres, *release.tags), alias_index)
        observed_weeks.add(week)
        for credit in release.artist_credits:
            key = _artist_key(credit.artist_name, credit.mbid, name_mbid_index)
            artist_memberships[key].update(genre_ids)
            artist_memberships[f"name:{normalize_alias(credit.artist_name)}"].update(
                genre_ids
            )
        for genre_id in genre_ids:
            cell = cells[(genre_id, week)]
            cell.releases.add(release.release_group_mbid)
            cell.timestamps.append(release.fetched_at)
            for credit in release.artist_credits:
                key = _artist_key(credit.artist_name, credit.mbid, name_mbid_index)
                cell.source_artists["musicbrainz"].add(key)

    posts = {post.uri: post for post in evidence.bluesky_posts}
    observed_weeks.update(iso_week_start(post.created_at) for post in posts.values())
    preferred_links: dict[str, PostLinkObservation] = {}
    for link in evidence.post_links:
        existing_link = preferred_links.get(link.post_uri)
        rank = (
            link.join_key_type.casefold() == "mbid",
            link.score,
            link.resolved_at,
        )
        if existing_link is None:
            preferred_links[link.post_uri] = link
            continue
        current_rank = (
            existing_link.join_key_type.casefold() == "mbid",
            existing_link.score,
            existing_link.resolved_at,
        )
        if rank > current_rank:
            preferred_links[link.post_uri] = link

    for post_uri, link in preferred_links.items():
        post = posts.get(post_uri)
        if post is None:
            continue
        week = iso_week_start(post.created_at)
        key = _artist_key(link.artist_name_raw, link.artist_mbid, name_mbid_index)
        genre_ids = artist_memberships.get(key, set())
        if not genre_ids:
            genre_ids = artist_memberships.get(
                f"name:{normalize_alias(link.artist_name_raw)}",
                set(),
            )
        for genre_id in genre_ids:
            cell = cells[(genre_id, week)]
            cell.resolved_posts.add(post_uri)
            cell.resolution_attempts.add(post_uri)
            cell.source_artists["bluesky"].add(key)
            cell.timestamps.extend((post.ingested_at, link.resolved_at))

    for ambiguity in evidence.post_ambiguities:
        if ambiguity.post_uri in preferred_links:
            continue
        post = posts.get(ambiguity.post_uri)
        if post is None:
            continue
        week = iso_week_start(post.created_at)
        key = _artist_key(
            ambiguity.top_artist_name,
            ambiguity.top_artist_mbid,
            name_mbid_index,
        )
        genre_ids = artist_memberships.get(key, set())
        if not genre_ids:
            genre_ids = artist_memberships.get(
                f"name:{normalize_alias(ambiguity.top_artist_name)}",
                set(),
            )
        for genre_id in genre_ids:
            cell = cells[(genre_id, week)]
            cell.resolution_attempts.add(ambiguity.post_uri)
            cell.timestamps.extend((post.ingested_at, ambiguity.resolved_at))

    weeks = _week_range(
        observed_weeks,
        thresholds.lookback_weeks,
        start_week,
        end_week,
    )
    macro_names = {
        macro.macro_family_id: macro.display_name for macro in taxonomy.macro_families
    }
    rows: list[GenreCoverageRow] = []
    max_age = timedelta(days=thresholds.max_source_age_days)
    for week in weeks:
        iso = week.isocalendar()
        for genre in taxonomy.genres:
            cell = cells[(genre.genre_id, week)]
            tag_available = True if cell.lastfm_tags else None
            unique_artists = len(cell.lastfm_artists) or None
            valid_artists = len(cell.valid_lastfm_artists) or None
            release_count = len(cell.releases) or None
            post_count = len(cell.resolved_posts) or None
            attempt_count = len(cell.resolution_attempts) or None
            resolution_rate = (
                len(cell.resolved_posts) / len(cell.resolution_attempts)
                if cell.resolution_attempts
                else None
            )
            source_sets = [
                artists for artists in cell.source_artists.values() if artists
            ]
            overlap_count: int | None = None
            overlap_rate: float | None = None
            if len(source_sets) >= 2:
                union = set().union(*source_sets)
                frequencies: dict[str, int] = defaultdict(int)
                for source_set in source_sets:
                    for artist_key in source_set:
                        frequencies[artist_key] += 1
                overlap_count = sum(count >= 2 for count in frequencies.values())
                overlap_rate = overlap_count / len(union) if union else None
            latest = max(cell.timestamps) if cell.timestamps else None
            stale = latest is None or computed_at - latest > max_age
            genre_history = sum(
                history_week <= week for history_week in history_weeks[genre.genre_id]
            )
            history_count = genre_history or None
            state = _eligibility(
                genre,
                cell,
                special_genre_ids=frozenset(
                    {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
                ),
                lastfm_tag_available=tag_available,
                unique_lastfm_artists=unique_artists,
                valid_lastfm_artists=valid_artists,
                history_weeks=history_count,
                release_count=release_count,
                post_count=post_count,
                resolution_attempts=attempt_count,
                resolution_rate=resolution_rate,
                overlap_count=overlap_count,
                overlap_rate=overlap_rate,
                stale=stale,
                thresholds=thresholds,
            )
            rows.append(
                GenreCoverageRow(
                    taxonomy_version=taxonomy.taxonomy_version,
                    week_start=week,
                    iso_year=iso.year,
                    iso_week=iso.week,
                    genre_id=genre.genre_id,
                    display_name=genre.display_name,
                    slug=genre.slug,
                    macro_family_id=genre.macro_family_id,
                    macro_family_name=macro_names[genre.macro_family_id],
                    taxonomy_status=genre.status,
                    lastfm_tag_available=tag_available,
                    unique_lastfm_artists=unique_artists,
                    artists_with_consecutive_valid_snapshots=valid_artists,
                    lastfm_history_weeks=history_count,
                    musicbrainz_release_group_count=release_count,
                    resolved_bluesky_post_count=post_count,
                    resolution_attempt_count=attempt_count,
                    resolution_rate=resolution_rate,
                    cross_source_overlap_artist_count=overlap_count,
                    cross_source_overlap=overlap_rate,
                    latest_source_timestamp=latest,
                    listening_missing=valid_artists is None,
                    conversation_missing=post_count is None,
                    supply_missing=release_count is None,
                    stale=stale,
                    eligibility_state=state,
                    computed_at=computed_at,
                )
            )
    return CoverageBatch(
        taxonomy_version=taxonomy.taxonomy_version,
        start_week=weeks[0] if weeks else None,
        end_week=weeks[-1] if weeks else None,
        computed_at=computed_at,
        rows=tuple(rows),
    )
