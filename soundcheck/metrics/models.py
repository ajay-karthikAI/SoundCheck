"""Validated metric evidence and mart row models."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class ConversationEvidence(BaseModel):
    """One resolved Bluesky post attributed to one canonical genre."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    canonical_genre: str
    post_uri: str
    mentions: int = Field(ge=0)
    likes: int = Field(ge=0)
    reposts: int = Field(ge=0)
    replies: int = Field(ge=0)

    @property
    def weighted_score(self) -> float:
        return (
            float(self.mentions)
            + 0.5 * self.likes
            + 1.5 * self.reposts
            + float(self.replies)
        )


class ListeningDeltaCandidate(BaseModel):
    """One consecutive-snapshot candidate before monotonicity validation."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    canonical_genre: str
    artist_key: str
    artist_name: str
    playcount: int = Field(ge=0)
    listeners: int = Field(ge=0)
    previous_playcount: int | None = Field(default=None, ge=0)
    previous_listeners: int | None = Field(default=None, ge=0)


class SupplyEvidence(BaseModel):
    """One MusicBrainz release group attributed to one canonical genre."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    canonical_genre: str
    release_group_mbid: str


class GenreWeekMetric(BaseModel):
    """One evidence-linked canonical-genre/ISO-week mart row."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    iso_year: int
    iso_week: int
    canonical_genre: str

    conversation_mentions: int
    conversation_likes: int
    conversation_reposts: int
    conversation_replies: int
    conversation_score_raw: float
    conversation_score_shrunk: float
    conversation_share_raw: float
    conversation_share_shrunk: float
    conversation_prior_share: float
    conversation_effective_n: float
    conversation_shrinkage_weight: float

    listening_playcount_delta: int | None
    listening_listeners_delta: int | None
    listening_score_raw: float | None

    supply_release_groups: int
    supply_rate_shrunk: float
    supply_prior_mean: float
    supply_effective_n: float
    supply_shrinkage_weight: float

    conversation_index: float
    conversation_index_ci_low: float
    conversation_index_ci_high: float
    listening_index: float | None
    listening_index_ci_low: float | None
    listening_index_ci_high: float | None
    supply_index: float
    supply_index_ci_low: float
    supply_index_ci_high: float
    opportunity: float | None
    opportunity_ci_low: float | None
    opportunity_ci_high: float | None
    discovery_gap: float | None
    discovery_gap_ci_low: float | None
    discovery_gap_ci_high: float | None

    conversation_ewma: float
    conversation_ewma_ci_low: float
    conversation_ewma_ci_high: float
    listening_ewma: float | None
    listening_ewma_ci_low: float | None
    listening_ewma_ci_high: float | None
    supply_ewma: float
    supply_ewma_ci_low: float
    supply_ewma_ci_high: float
    conversation_spike: bool
    listening_spike: bool
    supply_spike: bool
    breakout_precursor: bool

    conversation_post_uris: tuple[str, ...]
    listening_artist_keys: tuple[str, ...]
    supply_release_group_mbids: tuple[str, ...]
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)


class EcosystemWeekMetric(BaseModel):
    """One uncertainty-bearing ecosystem-health row."""

    model_config = ConfigDict(frozen=True)

    week_start: date
    iso_year: int
    iso_week: int
    shannon_listening_entropy: float | None
    shannon_listening_entropy_ci_low: float | None
    shannon_listening_entropy_ci_high: float | None
    effective_genres: float | None
    effective_genres_ci_low: float | None
    effective_genres_ci_high: float | None
    conversation_hhi: float | None
    conversation_hhi_ci_low: float | None
    conversation_hhi_ci_high: float | None
    listening_top10_share: float | None
    listening_top10_share_ci_low: float | None
    listening_top10_share_ci_high: float | None
    scene_churn_jaccard_4w: float | None
    scene_churn_jaccard_4w_ci_low: float | None
    scene_churn_jaccard_4w_ci_high: float | None
    breakout_genres: tuple[str, ...]
    canonical_genre_count: int
    listening_observed_genres: int
    opportunity_observed_genres: int
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)


class MetricEvidence(BaseModel):
    """Validated raw/staged evidence loaded for a full metrics rebuild."""

    model_config = ConfigDict(frozen=True)

    conversation: tuple[ConversationEvidence, ...]
    listening_candidates: tuple[ListeningDeltaCandidate, ...]
    supply: tuple[SupplyEvidence, ...]


class CanonicalGenreEmbedding(BaseModel):
    """One canonical embedding loaded for batch-only scene projection."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    embedding: tuple[float, ...]


class SceneMapPoint(BaseModel):
    """One precomputed UMAP point enriched with latest metric receipts."""

    model_config = ConfigDict(frozen=True)

    as_of_week: date
    canonical_genre: str
    x: float
    y: float
    opportunity: float | None
    opportunity_ci_low: float | None
    opportunity_ci_high: float | None
    discovery_gap: float | None
    discovery_gap_ci_low: float | None
    discovery_gap_ci_high: float | None
    evidence_volume: int = Field(ge=0)
    computed_at: datetime

    _computed_at_utc = field_validator("computed_at")(_as_utc)


class MetricsBatch(BaseModel):
    """Complete idempotent mart replacement."""

    model_config = ConfigDict(frozen=True)

    genre_weeks: tuple[GenreWeekMetric, ...]
    ecosystem_weeks: tuple[EcosystemWeekMetric, ...]
    scene_map_points: tuple[SceneMapPoint, ...] = ()
