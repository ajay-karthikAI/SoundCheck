"""Validated inputs and outputs for deterministic creator briefs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class BriefModel(BaseModel):
    """Closed immutable model for one brief pipeline boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class BriefCandidate(BriefModel):
    """A top-decile genre with a positive stored forecast."""

    week_start: date
    canonical_genre: str
    opportunity: float
    opportunity_ci_low: float
    opportunity_ci_high: float
    conversation_effective_n: float = Field(ge=0)
    supply_effective_n: float = Field(ge=0)
    supply_release_groups: int = Field(ge=0)
    typical_releases: float | None = Field(default=None, ge=0)
    release_range_low: int | None = Field(default=None, ge=0)
    release_range_high: int | None = Field(default=None, ge=0)
    release_history_weeks: int = Field(ge=0)
    target_week: date
    predicted_gain: float
    gain_interval_low: float
    gain_interval_high: float
    predicted_opportunity: float
    predicted_opportunity_interval_low: float
    predicted_opportunity_interval_high: float
    skill_status: Literal["skill", "no_skill"]

    @model_validator(mode="after")
    def validate_intervals(self) -> BriefCandidate:
        intervals = (
            (self.opportunity_ci_low, self.opportunity, self.opportunity_ci_high),
            (self.gain_interval_low, self.predicted_gain, self.gain_interval_high),
            (
                self.predicted_opportunity_interval_low,
                self.predicted_opportunity,
                self.predicted_opportunity_interval_high,
            ),
        )
        if any(not lower <= point <= upper for lower, point, upper in intervals):
            msg = "brief source intervals must contain their point estimates"
            raise ValueError(msg)
        return self


class BriefArtistEvidence(BriefModel):
    """A rising artist backed by consecutive Last.fm snapshot deltas."""

    artist_key: str
    artist_name: str
    artist_mbid: str | None
    playcount_delta: int = Field(ge=0)
    listeners_delta: int = Field(ge=0)
    weighted_delta: int = Field(gt=0)


class BriefConversationEvidence(BriefModel):
    """One linked representative Bluesky receipt."""

    post_uri: str
    did: str
    text: str
    weighted_score: float = Field(ge=0)


class BriefReleaseEvidence(BriefModel):
    """One linked MusicBrainz release-group receipt."""

    release_group_mbid: str
    title: str


class BriefSceneGenre(BriefModel):
    """One canonical genre vector and current release pressure."""

    canonical_genre: str
    embedding: tuple[float, ...]
    supply_index: float
    supply_release_groups: int = Field(ge=0)


class BriefEvidence(BriefModel):
    """All receipt types required for one credible creator note."""

    artists: tuple[BriefArtistEvidence, ...]
    conversation: BriefConversationEvidence | None
    releases: tuple[BriefReleaseEvidence, ...]


class BriefSourceBundle(BriefModel):
    """Complete batch input loaded from precomputed marts."""

    candidates: tuple[BriefCandidate, ...]
    evidence_by_genre: dict[str, BriefEvidence]
    scene_genres: tuple[BriefSceneGenre, ...]


class GeneratedBrief(BriefModel):
    """One frozen-contract creator brief ready for mart persistence."""

    brief_id: str
    week_start: date
    canonical_genre: str
    headline: str
    opportunity: float
    opportunity_ci_low: float
    opportunity_ci_high: float
    rationale: str
    recommended_actions: tuple[str, ...]
    evidence_uris: tuple[str, ...]
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)


class BriefBatch(BriefModel):
    """Generated output plus explicit suppression accounting."""

    briefs: tuple[GeneratedBrief, ...]
    candidate_count: int = Field(ge=0)
    suppressed_effective_n: int = Field(ge=0)
    suppressed_thin_evidence: int = Field(ge=0)
