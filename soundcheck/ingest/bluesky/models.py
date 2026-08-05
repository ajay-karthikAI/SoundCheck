"""Validated Bluesky and DuckDB boundary models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class Facet(BaseModel):
    """The subset of a rich-text facet needed by the classifier."""

    model_config = ConfigDict(extra="ignore")

    features: tuple[dict[str, Any], ...] = ()


class FeedPost(BaseModel):
    """A validated ``app.bsky.feed.post`` record."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    text: str
    created_at: datetime = Field(alias="createdAt")
    langs: tuple[str, ...] = ()
    facets: tuple[Facet, ...] = ()

    _created_at_utc = field_validator("created_at")(_as_utc)


class JetstreamCommit(BaseModel):
    """Commit metadata carried by Jetstream."""

    model_config = ConfigDict(extra="ignore")

    operation: str
    collection: str
    rkey: str
    record: dict[str, Any] | None = None


class JetstreamEvent(BaseModel):
    """A public Jetstream event."""

    model_config = ConfigDict(extra="ignore")

    did: str
    time_us: int = Field(ge=0)
    kind: str
    commit: JetstreamCommit | None = None


class RawBlueskyPost(BaseModel):
    """Append-only row for ``raw_.bluesky_posts``."""

    model_config = ConfigDict(frozen=True)

    uri: str
    did: str
    created_at: datetime
    text: str
    langs: tuple[str, ...]
    link_urls: tuple[str, ...]
    hashtags: tuple[str, ...]
    matched_rules: tuple[str, ...]
    ingested_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)
    _ingested_at_utc = field_validator("ingested_at")(_as_utc)


class AppViewPost(BaseModel):
    """Engagement fields returned by public AppView."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    uri: str
    like_count: int = Field(default=0, alias="likeCount", ge=0)
    repost_count: int = Field(default=0, alias="repostCount", ge=0)
    reply_count: int = Field(default=0, alias="replyCount", ge=0)


class AppViewGetPostsResponse(BaseModel):
    """Validated response from ``app.bsky.feed.getPosts``."""

    model_config = ConfigDict(extra="ignore")

    posts: tuple[AppViewPost, ...]


class EngagementSnapshot(BaseModel):
    """Append-only row for ``raw_.bluesky_engagement``."""

    model_config = ConfigDict(frozen=True)

    uri: str
    like_count: int = Field(ge=0)
    repost_count: int = Field(ge=0)
    reply_count: int = Field(ge=0)
    fetched_at: datetime

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)
