"""Validated Last.fm response and append-only snapshot models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


def _blank_to_none(value: object) -> object:
    if value == "":
        return None
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class TagInfo(BaseModel):
    """Cumulative Last.fm tag metadata."""

    model_config = ConfigDict(extra="ignore")

    name: str
    reach: int
    total: int = Field(validation_alias=AliasChoices("total", "taggings"))


class TagGetInfoResponse(BaseModel):
    """Response envelope for ``tag.getInfo``."""

    model_config = ConfigDict(extra="ignore")

    tag: TagInfo


class RankAttributes(BaseModel):
    """Last.fm list rank metadata."""

    model_config = ConfigDict(extra="ignore")

    rank: int


class TopArtist(BaseModel):
    """Artist reference from ``tag.getTopArtists``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    mbid: str | None = None
    rank_attributes: RankAttributes = Field(alias="@attr")

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class TopArtists(BaseModel):
    """Top-artist list payload."""

    model_config = ConfigDict(extra="ignore")

    artist: tuple[TopArtist, ...] = ()


class TagGetTopArtistsResponse(BaseModel):
    """Response envelope for ``tag.getTopArtists``."""

    model_config = ConfigDict(extra="ignore")

    topartists: TopArtists


class AlbumArtist(BaseModel):
    """Artist reference nested under a top album."""

    model_config = ConfigDict(extra="ignore")

    name: str
    mbid: str | None = None

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class TopAlbum(BaseModel):
    """Album reference from ``tag.getTopAlbums``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str
    mbid: str | None = None
    artist: AlbumArtist
    rank_attributes: RankAttributes = Field(alias="@attr")

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class TopAlbums(BaseModel):
    """Top-album list payload."""

    model_config = ConfigDict(extra="ignore")

    album: tuple[TopAlbum, ...] = ()


class TagGetTopAlbumsResponse(BaseModel):
    """Response envelope for ``tag.getTopAlbums``."""

    model_config = ConfigDict(extra="ignore")

    topalbums: TopAlbums = Field(
        validation_alias=AliasChoices("albums", "topalbums")
    )


class ArtistStats(BaseModel):
    """Cumulative artist totals, never weekly events."""

    model_config = ConfigDict(extra="ignore")

    listeners: int
    playcount: int = Field(validation_alias=AliasChoices("playcount", "plays"))


class ArtistTag(BaseModel):
    """One Last.fm artist tag."""

    model_config = ConfigDict(extra="ignore")

    name: str


class ArtistTags(BaseModel):
    """Artist tag list."""

    model_config = ConfigDict(extra="ignore")

    tag: tuple[ArtistTag, ...] = ()


class ArtistInfo(BaseModel):
    """Response artist from ``artist.getInfo``."""

    model_config = ConfigDict(extra="ignore")

    name: str
    mbid: str | None = None
    stats: ArtistStats
    tags: ArtistTags

    _normalize_mbid = field_validator("mbid", mode="before")(_blank_to_none)


class ArtistGetInfoResponse(BaseModel):
    """Response envelope for ``artist.getInfo``."""

    model_config = ConfigDict(extra="ignore")

    artist: ArtistInfo


class RankedArtist(BaseModel):
    """Evidence retained in a tag snapshot."""

    model_config = ConfigDict(frozen=True)

    name: str
    mbid: str | None
    rank: int


class RankedAlbum(BaseModel):
    """Album evidence retained in a tag snapshot."""

    model_config = ConfigDict(frozen=True)

    title: str
    mbid: str | None
    artist_name: str
    artist_mbid: str | None
    rank: int


class LastfmTagSnapshot(BaseModel):
    """Append-only cumulative tag observation."""

    model_config = ConfigDict(frozen=True)

    tag: str
    reach: int = Field(ge=0)
    total: int = Field(ge=0)
    top_artists: tuple[RankedArtist, ...]
    top_albums: tuple[RankedAlbum, ...]
    fetched_at: datetime

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)


class LastfmArtistSnapshot(BaseModel):
    """Append-only cumulative artist observation."""

    model_config = ConfigDict(frozen=True)

    artist_name: str
    mbid: str | None
    listeners: int = Field(ge=0)
    playcount: int = Field(ge=0)
    tags: tuple[str, ...]
    source_genres: tuple[str, ...]
    fetched_at: datetime

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)
