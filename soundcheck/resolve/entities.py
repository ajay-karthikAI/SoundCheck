"""Incrementally link Bluesky posts to artists with measured match scores."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import SplitResult, unquote_plus, urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from rapidfuzz.fuzz import token_set_ratio
from rapidfuzz.utils import default_process

from soundcheck.ingest.http import QueryValue
from soundcheck.ingest.lastfm.client import LastfmApiError
from soundcheck.ingest.lastfm.models import ArtistGetInfoResponse

MUSICBRAINZ_SCORE_THRESHOLD = 90.0
MUSICBRAINZ_AMBIGUITY_MARGIN = 3.0
LASTFM_SCORE_THRESHOLD = 92.0
LASTFM_MIN_NAME_LENGTH = 4
# artist.getInfo answers an unknown artist with error 6.
LASTFM_ARTIST_NOT_FOUND_ERROR = 6

_MBID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_QUOTED_NAME_PATTERNS = (
    re.compile(r'["“]([^"”]{2,100})["”]'),
    re.compile(r"(?<!\w)['\u2018]([^'\u2019\n]{2,100})['\u2019](?!\w)"),
)
_CAPITALIZED_WORD = (
    r"(?:[A-Z0-9](?:[\w\u2019'&.-]*[\w\u2019'&])?|of|the|and|&)"
)
_CAPITALIZED_NAME = rf"{_CAPITALIZED_WORD}(?:\s+{_CAPITALIZED_WORD}){{0,5}}"
_INTENT_NAME_PATTERNS = (
    re.compile(rf"(?i:\blistening\s+to\s+)(?P<name>{_CAPITALIZED_NAME})"),
    re.compile(rf"(?i:\bnew\s+)(?P<name>{_CAPITALIZED_NAME})(?i:\s+album\b)"),
    re.compile(rf"(?P<name>{_CAPITALIZED_NAME})(?i:\s+just\s+dropped\b)"),
)


class ResolutionApiClient(Protocol):
    """Shared shape of the official Last.fm and MusicBrainz clients."""

    async def get(
        self,
        method: str,
        params: Mapping[str, QueryValue],
    ) -> dict[str, JsonValue]:
        """Return one validated JSON object."""
        ...


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class RawResolutionPost(BaseModel):
    """Bluesky post boundary loaded from DuckDB."""

    model_config = ConfigDict(frozen=True)

    uri: str
    text: str
    link_urls: tuple[str, ...]


class LastfmArtistCandidate(BaseModel):
    """Latest Last.fm artist identity available for fuzzy fallback."""

    model_config = ConfigDict(frozen=True)

    artist_name: str
    mbid: str | None


class MusicBrainzAlias(BaseModel):
    """Artist alias returned by MusicBrainz search."""

    model_config = ConfigDict(extra="ignore")

    name: str


class MusicBrainzArtistCandidate(BaseModel):
    """Candidate identity returned by MusicBrainz artist search."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    aliases: tuple[MusicBrainzAlias, ...] = ()

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> object:
        return () if value is None else value


class MusicBrainzArtistSearchResponse(BaseModel):
    """Official MusicBrainz artist-search response."""

    model_config = ConfigDict(extra="ignore")

    artists: tuple[MusicBrainzArtistCandidate, ...] = ()


class PostArtistLink(BaseModel):
    """Accepted staged post-to-artist link."""

    model_config = ConfigDict(frozen=True)

    post_uri: str
    artist_mbid: str | None
    artist_name_raw: str
    method: str
    score: float = Field(ge=0, le=100)
    join_key_type: str
    resolved_at: datetime

    _resolved_at_utc = field_validator("resolved_at")(_as_utc)


class PostArtistAmbiguity(BaseModel):
    """Rejected close MusicBrainz candidate pair."""

    model_config = ConfigDict(frozen=True)

    post_uri: str
    artist_name_raw: str
    top_artist_mbid: str
    top_artist_name: str
    top_score: float
    second_artist_mbid: str
    second_artist_name: str
    second_score: float
    reason: str = "top_two_within_3_points"
    resolved_at: datetime

    _resolved_at_utc = field_validator("resolved_at")(_as_utc)


class ResolutionAttempt(BaseModel):
    """Idempotency marker for one post-resolution attempt."""

    model_config = ConfigDict(frozen=True)

    post_uri: str
    outcome: str
    candidate_count: int = Field(ge=0)
    attempted_at: datetime

    _attempted_at_utc = field_validator("attempted_at")(_as_utc)


class ResolutionBatch(BaseModel):
    """Results ready for one atomic staging write."""

    model_config = ConfigDict(frozen=True)

    links: tuple[PostArtistLink, ...]
    ambiguities: tuple[PostArtistAmbiguity, ...]
    attempts: tuple[ResolutionAttempt, ...]


class EntityResolutionStore(Protocol):
    """DuckDB operations required by the resolver."""

    async def initialize(self) -> None:
        """Create staging tables."""
        ...

    async def load_pending_posts(self) -> tuple[RawResolutionPost, ...]:
        """Load posts not previously attempted."""
        ...

    async def load_lastfm_artists(self) -> tuple[LastfmArtistCandidate, ...]:
        """Load the latest distinct Last.fm artist catalogue."""
        ...

    async def persist(self, batch: ResolutionBatch) -> tuple[int, int, int]:
        """Persist accepted, ambiguous, and attempted rows atomically."""
        ...


def extract_candidate_names(text: str) -> tuple[str, ...]:
    """Extract quoted names and capitalized n-grams adjacent to music intent."""
    candidates: list[tuple[int, str]] = []
    for pattern in _QUOTED_NAME_PATTERNS:
        candidates.extend(
            (match.start(), match.group(1))
            for match in pattern.finditer(text)
        )
    for pattern in _INTENT_NAME_PATTERNS:
        candidates.extend(
            (match.start(), match.group("name"))
            for match in pattern.finditer(text)
        )
    cleaned = (
        candidate.strip(" \t\r\n.,:;!?()[]{}")
        for _, candidate in sorted(candidates)
    )
    return tuple(dict.fromkeys(value for value in cleaned if len(value) >= 2))


def _split_url(url: str) -> SplitResult | None:
    # Stored link_urls are raw client-supplied facet URIs, some of which
    # urlsplit rejects (e.g. "https://NHL.com]").
    try:
        return urlsplit(url)
    except ValueError:
        return None


def direct_musicbrainz_mbid(url: str) -> str | None:
    """Extract an artist MBID only from a direct MusicBrainz artist URL."""
    parsed = _split_url(url)
    if parsed is None:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host != "musicbrainz.org" and not host.endswith(".musicbrainz.org"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "artist":
        return None
    mbid = parts[1]
    return mbid.casefold() if _MBID_RE.fullmatch(mbid) else None


def direct_lastfm_artist_name(url: str) -> str | None:
    """Extract an explicit artist name only from a Last.fm artist URL."""
    parsed = _split_url(url)
    if parsed is None:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host != "last.fm" and not host.endswith(".last.fm"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0].casefold() != "music":
        return None
    name = unquote_plus(parts[1]).strip()
    return name or None


async def resolve_entities(
    store: EntityResolutionStore,
    musicbrainz_client: ResolutionApiClient,
    lastfm_client: ResolutionApiClient,
    *,
    logger: logging.Logger | None = None,
    resolved_at: datetime | None = None,
) -> tuple[int, int, int]:
    """Run the ordered resolution ladder for every pending post."""
    await store.initialize()
    posts = await store.load_pending_posts()
    lastfm_artists = await store.load_lastfm_artists()
    resolution_time = resolved_at or datetime.now(UTC)
    accepted: list[PostArtistLink] = []
    ambiguities: list[PostArtistAmbiguity] = []
    attempts: list[ResolutionAttempt] = []

    for post in posts:
        post_links, post_ambiguities, candidate_count = await _resolve_post(
            post,
            musicbrainz_client,
            lastfm_client,
            lastfm_artists,
            resolution_time,
            logger,
        )
        accepted.extend(post_links)
        ambiguities.extend(post_ambiguities)
        outcome = "resolved" if post_links else "ambiguous" if post_ambiguities else "no_match"
        if candidate_count == 0 and not post_links:
            outcome = "no_candidate"
        attempts.append(
            ResolutionAttempt(
                post_uri=post.uri,
                outcome=outcome,
                candidate_count=candidate_count,
                attempted_at=resolution_time,
            )
        )

    return await store.persist(
        ResolutionBatch(
            links=tuple(accepted),
            ambiguities=tuple(ambiguities),
            attempts=tuple(attempts),
        )
    )


async def _resolve_post(
    post: RawResolutionPost,
    musicbrainz_client: ResolutionApiClient,
    lastfm_client: ResolutionApiClient,
    lastfm_artists: Sequence[LastfmArtistCandidate],
    resolved_at: datetime,
    logger: logging.Logger | None,
) -> tuple[list[PostArtistLink], list[PostArtistAmbiguity], int]:
    direct_links: list[PostArtistLink] = []
    linked_lastfm_names: list[str] = []
    for url in post.link_urls:
        mbid = direct_musicbrainz_mbid(url)
        if mbid is not None:
            direct_links.append(
                PostArtistLink(
                    post_uri=post.uri,
                    artist_mbid=mbid,
                    artist_name_raw=f"mbid:{mbid}",
                    method="direct_url",
                    score=100.0,
                    join_key_type="mbid",
                    resolved_at=resolved_at,
                )
            )
            continue
        lastfm_name = direct_lastfm_artist_name(url)
        if lastfm_name is None:
            continue
        linked_lastfm_names.append(lastfm_name)
        try:
            payload = await lastfm_client.get(
                "artist.getInfo",
                {"artist": lastfm_name, "autocorrect": 1},
            )
        except LastfmApiError as exc:
            if exc.code != LASTFM_ARTIST_NOT_FOUND_ERROR:
                raise
            continue
        artist = ArtistGetInfoResponse.model_validate(payload).artist
        if artist.mbid is not None:
            direct_links.append(
                PostArtistLink(
                    post_uri=post.uri,
                    artist_mbid=artist.mbid,
                    artist_name_raw=lastfm_name,
                    method="direct_url",
                    score=100.0,
                    join_key_type="mbid",
                    resolved_at=resolved_at,
                )
            )
    if direct_links:
        return direct_links, [], len(direct_links)

    candidates = tuple(
        dict.fromkeys((*extract_candidate_names(post.text), *linked_lastfm_names))
    )
    links: list[PostArtistLink] = []
    ambiguities: list[PostArtistAmbiguity] = []
    for candidate_name in candidates:
        link, ambiguity = await _resolve_with_musicbrainz(
            post.uri,
            candidate_name,
            musicbrainz_client,
            resolved_at,
        )
        if ambiguity is not None:
            ambiguities.append(ambiguity)
            _log_ambiguity(logger, ambiguity)
            continue
        if link is not None:
            links.append(link)
            continue
        fallback = _resolve_with_lastfm(
            post.uri,
            candidate_name,
            lastfm_artists,
            resolved_at,
        )
        if fallback is not None:
            links.append(fallback)
    return links, ambiguities, len(candidates)


async def _resolve_with_musicbrainz(
    post_uri: str,
    candidate_name: str,
    client: ResolutionApiClient,
    resolved_at: datetime,
) -> tuple[PostArtistLink | None, PostArtistAmbiguity | None]:
    escaped = candidate_name.replace("\\", "\\\\").replace('"', '\\"')
    payload = await client.get(
        "artist",
        {"query": f'artist:"{escaped}"', "limit": 10, "offset": 0},
    )
    response = MusicBrainzArtistSearchResponse.model_validate(payload)
    scored = sorted(
        (
            (
                max(
                    (
                        token_set_ratio(
                            candidate_name,
                            artist.name,
                            processor=default_process,
                        ),
                        *(
                            token_set_ratio(
                                candidate_name,
                                alias.name,
                                processor=default_process,
                            )
                            for alias in artist.aliases
                        ),
                    ),
                ),
                artist,
            )
            for artist in response.artists
        ),
        key=lambda value: value[0],
        reverse=True,
    )
    if not scored or scored[0][0] < MUSICBRAINZ_SCORE_THRESHOLD:
        return None, None
    top_score, top_artist = scored[0]
    if len(scored) > 1:
        second_score, second_artist = scored[1]
        if top_score - second_score <= MUSICBRAINZ_AMBIGUITY_MARGIN:
            return None, PostArtistAmbiguity(
                post_uri=post_uri,
                artist_name_raw=candidate_name,
                top_artist_mbid=top_artist.id,
                top_artist_name=top_artist.name,
                top_score=top_score,
                second_artist_mbid=second_artist.id,
                second_artist_name=second_artist.name,
                second_score=second_score,
                resolved_at=resolved_at,
            )
    return (
        PostArtistLink(
            post_uri=post_uri,
            artist_mbid=top_artist.id,
            artist_name_raw=candidate_name,
            method="musicbrainz_search",
            score=top_score,
            join_key_type="mbid",
            resolved_at=resolved_at,
        ),
        None,
    )


def _resolve_with_lastfm(
    post_uri: str,
    candidate_name: str,
    artists: Sequence[LastfmArtistCandidate],
    resolved_at: datetime,
) -> PostArtistLink | None:
    if len(candidate_name.strip()) < LASTFM_MIN_NAME_LENGTH or not artists:
        return None
    score, artist = max(
        (
            (
                token_set_ratio(
                    candidate_name,
                    artist.artist_name,
                    processor=default_process,
                ),
                artist,
            )
            for artist in artists
        ),
        key=lambda value: value[0],
    )
    if score < LASTFM_SCORE_THRESHOLD:
        return None
    return PostArtistLink(
        post_uri=post_uri,
        artist_mbid=artist.mbid,
        artist_name_raw=candidate_name,
        method="lastfm_fuzzy",
        score=score,
        join_key_type="mbid" if artist.mbid is not None else "name",
        resolved_at=resolved_at,
    )


def _log_ambiguity(
    logger: logging.Logger | None,
    ambiguity: PostArtistAmbiguity,
) -> None:
    if logger is None:
        return
    logger.info(
        json.dumps(
            {
                "event": "ambiguous_artist",
                "post_uri": ambiguity.post_uri,
                "artist_name_raw": ambiguity.artist_name_raw,
                "top_artist_mbid": ambiguity.top_artist_mbid,
                "top_score": ambiguity.top_score,
                "second_artist_mbid": ambiguity.second_artist_mbid,
                "second_score": ambiguity.second_score,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
