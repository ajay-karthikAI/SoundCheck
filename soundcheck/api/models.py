"""Frozen, validated response models for the public read-only API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type ForecastModelName = Literal[
    "naive",
    "seasonal_naive",
    "ets",
    "lightgbm",
]
type SkillStatus = Literal["baseline", "skill", "no_skill"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


def _as_optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)


class ApiModel(BaseModel):
    """Immutable API base model with a closed response schema."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EstimateBand(ApiModel):
    """A point estimate and its uncertainty bounds."""

    value: float
    lower: float
    upper: float

    @model_validator(mode="after")
    def validate_band(self) -> EstimateBand:
        if not self.lower <= self.value <= self.upper:
            msg = "uncertainty bounds must contain the point estimate"
            raise ValueError(msg)
        return self


class ShrinkageDiagnostics(ApiModel):
    """Axis-specific empirical Bayes diagnostics."""

    conversation: float = Field(ge=0, le=1)
    supply: float = Field(ge=0, le=1)


class EffectiveSampleSizes(ApiModel):
    """Axis-specific effective sample sizes after shrinkage."""

    conversation: float = Field(ge=0)
    supply: float = Field(ge=0)


class SpikeFlags(ApiModel):
    """Stored Phase 4 spike flags, without serving-time calculation."""

    conversation: bool
    listening: bool
    supply: bool


class PipelineRowsIngested(ApiModel):
    """Source-row counts observed during one pipeline run."""

    bluesky_posts: int = Field(ge=0)
    bluesky_engagement_snapshots: int = Field(ge=0)
    lastfm_tag_snapshots: int = Field(ge=0)
    lastfm_artist_snapshots: int = Field(ge=0)
    musicbrainz_release_groups: int = Field(ge=0)


class PipelineRunHealth(ApiModel):
    """Latest durable run manifest exposed without serving-time math."""

    run_id: str
    run_kind: Literal["daily", "weekly"]
    trigger: str
    git_sha: str | None
    status: Literal["running", "success", "failed"]
    started_at: datetime
    completed_at: datetime | None
    wall_time_seconds: float | None = Field(default=None, ge=0)
    rows_ingested: PipelineRowsIngested
    resolution_posts_attempted: int = Field(ge=0)
    resolution_links_resolved: int = Field(ge=0)
    resolution_rate: float | None = Field(default=None, ge=0, le=1)
    metric_rows: int = Field(ge=0)
    forecast_rows: int = Field(ge=0)
    brief_rows: int = Field(ge=0)
    error_message: str | None

    _started_at_utc = field_validator("started_at")(_as_utc)
    _completed_at_utc = field_validator("completed_at")(_as_optional_utc)


class HealthResponse(ApiModel):
    """Readiness and artifact recency for the read-only service."""

    status: Literal["ok"]
    datastore_mode: Literal["read_only"]
    latest_metric_week: date | None
    latest_forecast_week: date | None
    latest_complete_week: date | None
    metric_rows: int = Field(ge=0)
    forecast_rows: int = Field(ge=0)
    last_pipeline_run: PipelineRunHealth | None
    cache_ttl_seconds: int = Field(gt=0)


class OpportunityRow(ApiModel):
    """One decision-ready genre opportunity row."""

    week: date
    genre: str
    opportunity: EstimateBand
    discovery_gap: EstimateBand
    z_conversation: EstimateBand
    z_listening: EstimateBand
    z_supply: EstimateBand
    shrinkage_weight: ShrinkageDiagnostics
    effective_n: EffectiveSampleSizes
    spike_flag: SpikeFlags
    breakout_flag: bool


class TrendAxisPoint(ApiModel):
    """Historical axis point with its EWMA and uncertainty."""

    index: EstimateBand
    ewma: EstimateBand
    spike: bool


class GenreHistoryPoint(ApiModel):
    """One stored genre-week history point."""

    week: date
    conversation: TrendAxisPoint
    listening: TrendAxisPoint | None
    supply: TrendAxisPoint
    opportunity: EstimateBand | None
    discovery_gap: EstimateBand | None


class GenreForecastPoint(ApiModel):
    """One selected axis forecast and its published validation."""

    target_week: date
    target_axis: Literal["conversation", "listening"]
    horizon: int = Field(ge=1, le=2)
    model: ForecastModelName
    skill_status: SkillStatus
    prediction_interval_80: EstimateBand
    backtest_mase: float | None = Field(default=None, ge=0)
    backtest_coverage_80: float = Field(ge=0, le=1)
    backtest_origins: int = Field(gt=0)


class GenreTimeseriesResponse(ApiModel):
    """Historical points followed by independently validated forecasts."""

    genre: str
    history: tuple[GenreHistoryPoint, ...]
    forecasts: tuple[GenreForecastPoint, ...]


class BlueskyEvidence(ApiModel):
    """One resolved Bluesky receipt."""

    uri: str
    did: str
    created_at: datetime
    text: str
    likes: int = Field(ge=0)
    reposts: int = Field(ge=0)
    replies: int = Field(ge=0)
    artist_name_raw: str
    resolution_method: str
    resolution_score: float = Field(ge=0, le=100)
    join_key_type: str

    _created_at_utc = field_validator("created_at")(_as_utc)


class BlueskyFeedPost(ApiModel):
    """One publication-eligible public Bluesky music post."""

    uri: str
    did: str
    created_at: datetime
    text: str
    link_urls: tuple[str, ...]
    hashtags: tuple[str, ...]
    matched_rules: tuple[str, ...]
    likes: int = Field(ge=0)
    reposts: int = Field(ge=0)
    replies: int = Field(ge=0)

    _created_at_utc = field_validator("created_at")(_as_utc)


class LastfmEvidence(ApiModel):
    """One artist's validated consecutive-snapshot weekly deltas."""

    artist_key: str
    artist_name: str
    artist_mbid: str | None
    playcount_delta: int = Field(ge=0)
    listeners_delta: int = Field(ge=0)
    previous_fetched_at: datetime | None
    fetched_at: datetime
    interval_days: float | None = Field(default=None, gt=0)
    listening_window_status: Literal["valid_weekly", "legacy_unvalidated"]

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)
    _previous_fetched_at_utc = field_validator("previous_fetched_at")(
        lambda value: None if value is None else _as_utc(value)
    )


class ArtistCredit(ApiModel):
    """One MusicBrainz artist credit."""

    credit_name: str
    artist_name: str
    mbid: str | None
    join_phrase: str


class MusicBrainzEvidence(ApiModel):
    """One first-release supply receipt."""

    release_group_mbid: str
    title: str
    artist_credits: tuple[ArtistCredit, ...]
    first_release_date: date
    types: tuple[str, ...]
    genres: tuple[str, ...]


class GenreEvidenceResponse(ApiModel):
    """Raw receipts for one genre-week metric row."""

    genre: str
    week: date
    bluesky_posts: tuple[BlueskyEvidence, ...]
    lastfm_artists: tuple[LastfmEvidence, ...]
    musicbrainz_releases: tuple[MusicBrainzEvidence, ...]


class BacktestedModel(ApiModel):
    """Selected model identity and its historical error."""

    name: ForecastModelName
    mase: float | None = Field(default=None, ge=0)


class NextUpRow(ApiModel):
    """Breakout-filtered predicted opportunity gain."""

    origin_week: date
    target_week: date
    genre: str
    rank: int = Field(gt=0)
    predicted_opportunity: EstimateBand
    predicted_gain: EstimateBand
    conversation_model: BacktestedModel
    listening_model: BacktestedModel
    skill_status: Literal["skill", "no_skill"]
    breakout_evidence_week: date


class EcosystemPoint(ApiModel):
    """One uncertainty-bearing ecosystem-health week."""

    week: date
    listening_entropy: EstimateBand | None
    effective_genres: EstimateBand | None
    conversation_hhi: EstimateBand | None
    listening_top10_share: EstimateBand | None
    scene_churn_jaccard_4w: EstimateBand | None
    breakout_genres: tuple[str, ...]
    canonical_genre_count: int = Field(ge=0)
    listening_observed_genres: int = Field(ge=0)
    opportunity_observed_genres: int = Field(ge=0)


class CreatorBrief(ApiModel):
    """Frozen Phase 8 creator-brief item shape."""

    brief_id: str
    week: date
    genre: str
    headline: str
    opportunity: EstimateBand
    rationale: str
    recommended_actions: tuple[str, ...]
    evidence_uris: tuple[str, ...]
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)


class SceneMapPoint(ApiModel):
    """One precomputed UMAP point for the latest scene."""

    as_of_week: date
    genre: str
    x: float
    y: float
    opportunity: EstimateBand | None
    discovery_gap: EstimateBand | None
    evidence_volume: int = Field(ge=0)


class ApiErrorDetail(ApiModel):
    """Stable machine-readable error detail."""

    code: str
    message: str


class ApiError(ApiModel):
    """Stable FastAPI error envelope."""

    detail: ApiErrorDetail
