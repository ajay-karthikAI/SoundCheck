"""Validated taxonomy-v2 metric evidence and parallel mart artifacts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from soundcheck.metrics.coverage import EligibilityState, GenreCoverageRow

MetricContext = Literal["global", "peer_family"]
MetricName = Literal[
    "conversation",
    "listening",
    "supply",
    "opportunity",
    "discovery_gap",
]
ScopeType = Literal["genre", "macro_family"]
EstimateStatus = Literal[
    "ready",
    "collecting_history",
    "insufficient_listening",
    "insufficient_conversation",
    "insufficient_supply",
    "insufficient_resolution",
    "unsupported",
    "evidence_mismatch",
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class ConversationEvidenceV2(BaseModel):
    """One resolved post weighted by one artist's v2 genre membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: date
    genre_id: str
    macro_family_id: str
    post_uri: str
    membership_weight: float = Field(gt=0.0, le=1.0)
    likes: int = Field(ge=0)
    reposts: int = Field(ge=0)
    replies: int = Field(ge=0)
    did: str | None = None
    created_at: datetime | None = None
    text: str | None = None
    artist_name_raw: str | None = None
    resolution_method: str | None = None
    resolution_score: float | None = Field(default=None, ge=0.0, le=100.0)
    join_key_type: str | None = None
    membership_method: str | None = None
    membership_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def weighted_score(self) -> float:
        return self.membership_weight * (
            1.0 + 0.5 * self.likes + 1.5 * self.reposts + self.replies
        )


class ListeningCandidateV2(BaseModel):
    """One weekly Last.fm snapshot joined to a v2 artist membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: date
    genre_id: str
    macro_family_id: str
    artist_key: str
    membership_weight: float = Field(gt=0.0, le=1.0)
    playcount: int = Field(ge=0)
    listeners: int = Field(ge=0)
    previous_playcount: int | None = Field(default=None, ge=0)
    previous_listeners: int | None = Field(default=None, ge=0)
    artist_name: str | None = None
    artist_mbid: str | None = None
    fetched_at: datetime | None = None
    previous_fetched_at: datetime | None = None
    membership_method: str | None = None
    membership_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SupplyEvidenceV2(BaseModel):
    """One release group's normalized v2 genre attribution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    week_start: date
    genre_id: str
    macro_family_id: str
    release_group_mbid: str
    membership_weight: float = Field(gt=0.0, le=1.0)
    title: str | None = None
    artist_credits: tuple[dict[str, str | None], ...] = ()
    first_release_date: date | None = None
    types: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    fetched_at: datetime | None = None


class ConversationReceiptV2(BaseModel):
    """One materialized Bluesky receipt behind a v2 genre-week."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    genre_id: str
    macro_family_id: str
    post_uri: str
    did: str
    created_at: datetime
    text: str
    likes: int = Field(ge=0)
    reposts: int = Field(ge=0)
    replies: int = Field(ge=0)
    artist_name_raw: str
    resolution_method: str
    resolution_score: float = Field(ge=0.0, le=100.0)
    join_key_type: str
    membership_weight: float = Field(gt=0.0, le=1.0)
    membership_method: str
    membership_confidence: float = Field(ge=0.0, le=1.0)

    _created_at_utc = field_validator("created_at")(_as_utc)


class ListeningReceiptV2(BaseModel):
    """One materialized consecutive-snapshot Last.fm receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    genre_id: str
    macro_family_id: str
    artist_key: str
    artist_name: str
    artist_mbid: str | None
    playcount: int = Field(ge=0)
    listeners: int = Field(ge=0)
    previous_playcount: int = Field(ge=0)
    previous_listeners: int = Field(ge=0)
    playcount_delta: int = Field(ge=0)
    listeners_delta: int = Field(ge=0)
    fetched_at: datetime
    previous_fetched_at: datetime
    membership_weight: float = Field(gt=0.0, le=1.0)
    membership_method: str
    membership_confidence: float = Field(ge=0.0, le=1.0)

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)
    _previous_fetched_at_utc = field_validator("previous_fetched_at")(_as_utc)


class SupplyReceiptV2(BaseModel):
    """One materialized MusicBrainz release-group receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    genre_id: str
    macro_family_id: str
    release_group_mbid: str
    title: str
    artist_credits: tuple[dict[str, str | None], ...]
    first_release_date: date
    types: tuple[str, ...]
    genres: tuple[str, ...]
    fetched_at: datetime
    membership_weight: float = Field(gt=0.0, le=1.0)

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)


class MetricEvidenceV2(BaseModel):
    """Validated evidence plus the version-matched coverage grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    conversation: tuple[ConversationEvidenceV2, ...] = ()
    listening_candidates: tuple[ListeningCandidateV2, ...] = ()
    supply: tuple[SupplyEvidenceV2, ...] = ()
    coverage: tuple[GenreCoverageRow, ...] = ()


class GenreWeekV2(BaseModel):
    """Coverage, evidence, and hierarchical-prior state for one genre-week."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    iso_year: int
    iso_week: int = Field(ge=1, le=53)
    genre_id: str
    display_name: str
    macro_family_id: str
    parent_genre_id: str | None
    coverage_state: EligibilityState
    estimate_status: EstimateStatus
    estimate_eligible: bool

    conversation_score_raw: float | None = Field(default=None, ge=0.0)
    listening_playcount_delta: float | None = Field(default=None, ge=0.0)
    listening_listeners_delta: float | None = Field(default=None, ge=0.0)
    listening_score_raw: float | None = Field(default=None, ge=0.0)
    supply_release_groups_raw: float | None = Field(default=None, ge=0.0)

    conversation_score_shrunk: float | None = Field(default=None, ge=0.0)
    conversation_effective_n: float | None = Field(default=None, ge=0.0)
    conversation_subgenre_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    conversation_family_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    conversation_combined_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    listening_effective_n: float | None = Field(default=None, ge=0.0)
    listening_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    supply_rate_shrunk: float | None = Field(default=None, ge=0.0)
    supply_family_prior_mean: float | None = Field(default=None, ge=0.0)
    supply_global_prior_mean: float | None = Field(default=None, ge=0.0)
    supply_effective_n: float | None = Field(default=None, ge=0.0)
    supply_subgenre_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    supply_family_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    supply_combined_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    breakout_global: bool | None
    breakout_peer_family: bool | None
    conversation_post_uris: tuple[str, ...]
    listening_artist_keys: tuple[str, ...]
    supply_release_group_mbids: tuple[str, ...]
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)

    @model_validator(mode="after")
    def validate_missingness(self) -> GenreWeekV2:
        estimates = (
            self.conversation_score_raw,
            self.listening_score_raw,
            self.supply_release_groups_raw,
            self.conversation_score_shrunk,
            self.supply_rate_shrunk,
        )
        if not self.estimate_eligible and any(value is not None for value in estimates):
            raise ValueError("ineligible genre-weeks must keep estimates null")
        if self.estimate_eligible and self.estimate_status != "ready":
            raise ValueError("eligible estimates must have ready status")
        return self


class MetricEstimateV2(BaseModel):
    """One uncertainty-bearing context-specific metric estimate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    scope_type: ScopeType
    scope_id: str
    macro_family_id: str
    context: MetricContext
    metric_name: MetricName
    estimate_status: EstimateStatus
    estimate: float | None
    ci_low: float | None
    ci_high: float | None
    ewma: float | None
    ewma_ci_low: float | None
    ewma_ci_high: float | None
    spike: bool | None
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)

    @model_validator(mode="after")
    def validate_intervals(self) -> MetricEstimateV2:
        self._validate_interval(self.estimate, self.ci_low, self.ci_high, "estimate")
        self._validate_interval(
            self.ewma,
            self.ewma_ci_low,
            self.ewma_ci_high,
            "ewma",
        )
        if self.estimate is None and self.spike is not None:
            raise ValueError("missing estimates cannot carry spike flags")
        return self

    @staticmethod
    def _validate_interval(
        point: float | None,
        low: float | None,
        high: float | None,
        label: str,
    ) -> None:
        if point is None:
            if low is not None or high is not None:
                raise ValueError(f"missing {label} must have a null interval")
            return
        if low is None or high is None or not low <= point <= high:
            raise ValueError(f"{label} interval must contain its point")


class MacroFamilyWeekV2(BaseModel):
    """One macro-family/ISO-week aggregate and its evidence eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    iso_year: int
    iso_week: int = Field(ge=1, le=53)
    macro_family_id: str
    display_name: str
    total_genres: int = Field(ge=1)
    eligible_genres: int = Field(ge=0)
    estimate_status: Literal["ready", "insufficient_evidence"]
    coverage_state_counts_json: str
    conversation_score_raw: float | None = Field(default=None, ge=0.0)
    listening_score_raw: float | None = Field(default=None, ge=0.0)
    supply_release_groups_raw: float | None = Field(default=None, ge=0.0)
    conversation_effective_n: float | None = Field(default=None, ge=0.0)
    listening_effective_n: float | None = Field(default=None, ge=0.0)
    supply_effective_n: float | None = Field(default=None, ge=0.0)
    breakout_genres_global: tuple[str, ...]
    breakout_genres_peer: tuple[str, ...]
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)


class EcosystemWeekV2(BaseModel):
    """Global or family-local ecosystem health with uncertainty."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    week_start: date
    iso_year: int
    iso_week: int = Field(ge=1, le=53)
    scope_type: Literal["global", "macro_family"]
    scope_id: str
    estimate_status: Literal["ready", "insufficient_evidence"]
    listening_entropy: float | None
    listening_entropy_ci_low: float | None
    listening_entropy_ci_high: float | None
    effective_genres: float | None
    effective_genres_ci_low: float | None
    effective_genres_ci_high: float | None
    conversation_hhi: float | None
    conversation_hhi_ci_low: float | None
    conversation_hhi_ci_high: float | None
    listening_top_share: float | None
    listening_top_share_ci_low: float | None
    listening_top_share_ci_high: float | None
    listening_top_share_k: int
    churn_jaccard_4w: float | None
    churn_jaccard_4w_ci_low: float | None
    churn_jaccard_4w_ci_high: float | None
    breakout_genres: tuple[str, ...]
    eligible_genres: int = Field(ge=0)
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)

    @model_validator(mode="after")
    def validate_intervals(self) -> EcosystemWeekV2:
        for label, point, low, high in (
            (
                "listening_entropy",
                self.listening_entropy,
                self.listening_entropy_ci_low,
                self.listening_entropy_ci_high,
            ),
            (
                "effective_genres",
                self.effective_genres,
                self.effective_genres_ci_low,
                self.effective_genres_ci_high,
            ),
            (
                "conversation_hhi",
                self.conversation_hhi,
                self.conversation_hhi_ci_low,
                self.conversation_hhi_ci_high,
            ),
            (
                "listening_top_share",
                self.listening_top_share,
                self.listening_top_share_ci_low,
                self.listening_top_share_ci_high,
            ),
            (
                "churn",
                self.churn_jaccard_4w,
                self.churn_jaccard_4w_ci_low,
                self.churn_jaccard_4w_ci_high,
            ),
        ):
            MetricEstimateV2._validate_interval(point, low, high, label)
        return self


class MetricsV2Batch(BaseModel):
    """One taxonomy version's replaceable artifacts; v1 is never included."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    genre_weeks: tuple[GenreWeekV2, ...]
    macro_family_weeks: tuple[MacroFamilyWeekV2, ...]
    estimates: tuple[MetricEstimateV2, ...]
    ecosystem_weeks: tuple[EcosystemWeekV2, ...]
    conversation_evidence: tuple[ConversationReceiptV2, ...] = ()
    listening_evidence: tuple[ListeningReceiptV2, ...] = ()
    supply_evidence: tuple[SupplyReceiptV2, ...] = ()

    @model_validator(mode="after")
    def validate_version_isolation(self) -> MetricsV2Batch:
        versions = (
            *(row.taxonomy_version for row in self.genre_weeks),
            *(row.taxonomy_version for row in self.macro_family_weeks),
            *(row.taxonomy_version for row in self.estimates),
            *(row.taxonomy_version for row in self.ecosystem_weeks),
            *(row.taxonomy_version for row in self.conversation_evidence),
            *(row.taxonomy_version for row in self.listening_evidence),
            *(row.taxonomy_version for row in self.supply_evidence),
        )
        if any(version != self.taxonomy_version for version in versions):
            raise ValueError("every v2 mart row must match the batch taxonomy version")
        return self
