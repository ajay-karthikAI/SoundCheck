"""Operational source-maturity models and genre-week gating helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PostEngagementMaturityStatus = Literal[
    "awaiting_24h",
    "overdue_24h",
    "awaiting_72h",
    "overdue_72h",
    "complete",
]
ConversationMaturity = Literal["conversation_pending", "complete"]
ListeningMaturity = Literal["listening_pending", "complete"]
SupplyMaturity = Literal["supply_pending", "complete"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class PostEngagementMaturity(BaseModel):
    """One post's immutable-poll maturity as observed by a metrics batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    post_uri: str
    created_at: datetime
    as_of: datetime
    has_24h_snapshot: bool
    has_72h_snapshot: bool
    latest_engagement_fetched_at: datetime | None = None
    like_count: int | None = Field(default=None, ge=0)
    repost_count: int | None = Field(default=None, ge=0)
    reply_count: int | None = Field(default=None, ge=0)
    engagement_maturity_status: PostEngagementMaturityStatus

    _created_at_utc = field_validator("created_at")(_as_utc)
    _as_of_utc = field_validator("as_of")(_as_utc)
    _latest_fetched_at_utc = field_validator("latest_engagement_fetched_at")(
        lambda value: None if value is None else _as_utc(value)
    )

    @model_validator(mode="after")
    def validate_missingness(self) -> PostEngagementMaturity:
        counts = (self.like_count, self.repost_count, self.reply_count)
        if self.engagement_maturity_status == "complete":
            if not self.has_72h_snapshot or any(value is None for value in counts):
                raise ValueError("complete engagement requires a 72h snapshot and counts")
        elif any(value is not None for value in counts):
            raise ValueError("pending engagement counts must remain null")
        return self


class SupplyCollectionWindow(BaseModel):
    """One fully completed, bounded MusicBrainz first-release-date query window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_date: date
    end_date: date
    completed_at: datetime

    _completed_at_utc = field_validator("completed_at")(_as_utc)

    @model_validator(mode="after")
    def validate_window(self) -> SupplyCollectionWindow:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class GenreWeekAxisMaturity(BaseModel):
    """Per-axis operational maturity for one genre and ISO week."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_family: Literal["v1", "v2"]
    taxonomy_version: str
    week_start: date
    genre_id: str
    conversation_maturity: ConversationMaturity
    listening_maturity: ListeningMaturity
    supply_maturity: SupplyMaturity
    decision_ready: bool
    conversation_post_count: int = Field(ge=0)
    mature_conversation_post_count: int = Field(ge=0)
    valid_listening_artist_count: int = Field(ge=0)
    supply_release_group_count: int = Field(ge=0)
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)

    @model_validator(mode="after")
    def validate_decision_gate(self) -> GenreWeekAxisMaturity:
        expected = (
            self.conversation_maturity == "complete"
            and self.listening_maturity == "complete"
            and self.supply_maturity == "complete"
        )
        if self.decision_ready != expected:
            raise ValueError("decision_ready must require all three complete axes")
        if self.mature_conversation_post_count > self.conversation_post_count:
            raise ValueError("mature post count cannot exceed total post count")
        return self


class ConversationMaturityEvidence(Protocol):
    """Fields required from v1 or v2 conversation evidence."""

    @property
    def week_start(self) -> date: ...

    @property
    def post_uri(self) -> str: ...

    @property
    def engagement_maturity_status(self) -> PostEngagementMaturityStatus: ...


class ListeningMaturityEvidence(Protocol):
    """Fields required from v1 or v2 listening evidence."""

    @property
    def week_start(self) -> date: ...

    @property
    def artist_key(self) -> str: ...

    @property
    def listening_window_status(self) -> str | None: ...


class SupplyMaturityEvidence(Protocol):
    """Fields required from v1 or v2 supply evidence."""

    @property
    def week_start(self) -> date: ...

    @property
    def release_group_mbid(self) -> str: ...


def complete_supply_weeks(
    windows: tuple[SupplyCollectionWindow, ...],
    weeks: tuple[date, ...],
    *,
    as_of: datetime,
) -> frozenset[date]:
    """Return closed ISO weeks wholly covered by a completed source window."""

    current_week = as_of.astimezone(UTC).date()
    current_week -= timedelta(days=current_week.weekday())
    complete: set[date] = set()
    for week in weeks:
        week_end = week + timedelta(days=6)
        if week >= current_week:
            continue
        if any(
            window.start_date <= week and window.end_date >= week_end
            for window in windows
        ):
            complete.add(week)
    return frozenset(complete)


def build_axis_maturity(
    *,
    artifact_family: Literal["v1", "v2"],
    taxonomy_version: str,
    weeks: tuple[date, ...],
    genre_ids: tuple[str, ...],
    conversation: tuple[tuple[str, ConversationMaturityEvidence], ...],
    listening: tuple[tuple[str, ListeningMaturityEvidence], ...],
    supply: tuple[tuple[str, SupplyMaturityEvidence], ...],
    supply_windows: tuple[SupplyCollectionWindow, ...],
    computed_at: datetime,
) -> tuple[GenreWeekAxisMaturity, ...]:
    """Build strict per-axis maturity receipts for a taxonomy grid."""

    conversation_by_cell: dict[tuple[date, str], dict[str, str]] = defaultdict(dict)
    for genre_id, conversation_item in conversation:
        conversation_by_cell[
            (conversation_item.week_start, genre_id)
        ][conversation_item.post_uri] = (
            conversation_item.engagement_maturity_status
        )
    listening_by_cell: dict[tuple[date, str], set[str]] = defaultdict(set)
    for genre_id, listening_item in listening:
        if listening_item.listening_window_status == "valid_weekly":
            listening_by_cell[(listening_item.week_start, genre_id)].add(
                listening_item.artist_key
            )
    supply_by_cell: dict[tuple[date, str], set[str]] = defaultdict(set)
    for genre_id, supply_item in supply:
        supply_by_cell[(supply_item.week_start, genre_id)].add(
            supply_item.release_group_mbid
        )

    closed_supply = complete_supply_weeks(
        supply_windows,
        weeks,
        as_of=computed_at,
    )
    rows: list[GenreWeekAxisMaturity] = []
    for week in weeks:
        for genre_id in genre_ids:
            key = (week, genre_id)
            post_states = conversation_by_cell.get(key, {})
            mature_posts = sum(state == "complete" for state in post_states.values())
            conversation_status: ConversationMaturity = (
                "complete"
                if post_states and mature_posts == len(post_states)
                else "conversation_pending"
            )
            listening_artists = listening_by_cell.get(key, set())
            listening_status: ListeningMaturity = (
                "complete" if listening_artists else "listening_pending"
            )
            supply_status: SupplyMaturity = (
                "complete" if week in closed_supply else "supply_pending"
            )
            rows.append(
                GenreWeekAxisMaturity(
                    artifact_family=artifact_family,
                    taxonomy_version=taxonomy_version,
                    week_start=week,
                    genre_id=genre_id,
                    conversation_maturity=conversation_status,
                    listening_maturity=listening_status,
                    supply_maturity=supply_status,
                    decision_ready=(
                        conversation_status == "complete"
                        and listening_status == "complete"
                        and supply_status == "complete"
                    ),
                    conversation_post_count=len(post_states),
                    mature_conversation_post_count=mature_posts,
                    valid_listening_artist_count=len(listening_artists),
                    supply_release_group_count=len(supply_by_cell.get(key, set())),
                    computed_at=computed_at,
                )
            )
    return tuple(rows)
