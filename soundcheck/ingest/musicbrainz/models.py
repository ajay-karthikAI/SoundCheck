"""Validated MusicBrainz response and raw release-group models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class MusicBrainzTag(BaseModel):
    """A counted MusicBrainz tag or genre."""

    model_config = ConfigDict(extra="ignore")

    name: str
    count: int = 0


class MusicBrainzArtist(BaseModel):
    """Artist identity nested in an artist credit."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class MusicBrainzArtistCredit(BaseModel):
    """Credited artist name, identity, and join phrase."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    artist: MusicBrainzArtist
    join_phrase: str = Field(default="", alias="joinphrase")


class MusicBrainzReleaseGroup(BaseModel):
    """Release-group search result with requested includes."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    title: str
    first_release_date: str = Field(alias="first-release-date")
    primary_type: str | None = Field(default=None, alias="primary-type")
    secondary_types: tuple[str, ...] = Field(default=(), alias="secondary-types")
    artist_credit: tuple[MusicBrainzArtistCredit, ...] = Field(alias="artist-credit")
    genres: tuple[MusicBrainzTag, ...] = ()
    tags: tuple[MusicBrainzTag, ...] = ()


class ReleaseGroupSearchResponse(BaseModel):
    """Paginated release-group search response."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    count: int = Field(ge=0)
    offset: int = Field(ge=0)
    release_groups: tuple[MusicBrainzReleaseGroup, ...] = Field(alias="release-groups")


class ArtistCreditRecord(BaseModel):
    """Artist credit retained in DuckDB."""

    model_config = ConfigDict(frozen=True)

    credit_name: str
    artist_name: str
    mbid: str
    join_phrase: str


class TagCountRecord(BaseModel):
    """Counted tag retained in DuckDB."""

    model_config = ConfigDict(frozen=True)

    name: str
    count: int


class RawMusicBrainzReleaseGroup(BaseModel):
    """Insert-on-first-sight MusicBrainz supply record."""

    model_config = ConfigDict(frozen=True)

    release_group_mbid: str
    title: str
    artist_credits: tuple[ArtistCreditRecord, ...]
    artist_mbids: tuple[str, ...]
    first_release_date: str
    types: tuple[str, ...]
    genres: tuple[str, ...]
    tags: tuple[TagCountRecord, ...]
    fetched_at: datetime

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)

