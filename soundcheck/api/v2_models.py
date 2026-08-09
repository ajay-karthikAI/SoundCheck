"""Frozen response models for the non-breaking Soundcheck API v2 contract."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from soundcheck.api.models import ApiModel, ArtistCredit, EstimateBand

ComparisonContextV2 = Literal["global", "peer_family"]
CoverageStatusV2 = Literal[
    "ready",
    "collecting_history",
    "insufficient_listening",
    "insufficient_conversation",
    "insufficient_supply",
    "insufficient_resolution",
    "unsupported",
    "not_observed",
]
TaxonomyStatusV2 = Literal["enabled", "candidate", "rejected"]
ForecastStatusV2 = Literal[
    "ready",
    "no_skill",
    "insufficient_history",
    "insufficient_evidence",
]
ForecastModelV2 = Literal["naive", "seasonal_naive", "ets", "lightgbm"]
ScoreStatusV2 = Literal[
    "scored",
    "zero_naive_scale",
    "insufficient_history",
    "unavailable_model",
]
EvidenceSourceV2 = Literal["conversation", "listening", "supply"]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class CursorPageMeta(ApiModel):
    """Opaque continuation state for a deterministic result page."""

    next_cursor: str | None
    has_more: bool


class MacroFamilyV2(ApiModel):
    """Stable macro-family taxonomy identity."""

    macro_family_id: str
    display_name: str
    slug: str


class GenreIdentityV2(ApiModel):
    """Required stable identity and current evidence state for every genre row."""

    genre_id: str
    slug: str
    display_name: str
    macro_family_id: str
    macro_family_name: str
    parent_genre_id: str | None
    taxonomy_version: str
    taxonomy_status: TaxonomyStatusV2
    coverage_status: CoverageStatusV2


class GenreCatalogPageV2(ApiModel):
    """Cursor-paginated taxonomy or search results."""

    items: tuple[GenreIdentityV2, ...]
    page: CursorPageMeta


class TaxonomyResponseV2(ApiModel):
    """One deployed taxonomy version and a filtered genre page."""

    taxonomy_version: str
    default_genre_id: str
    other_genre_id: str
    unresolved_genre_id: str
    genres: GenreCatalogPageV2


class MacroFamilyPageV2(ApiModel):
    """The stable macro families in one deployed taxonomy."""

    taxonomy_version: str
    items: tuple[MacroFamilyV2, ...]
    page: CursorPageMeta


class OpportunityDiagnosticsV2(ApiModel):
    """Stored v2 effective samples and hierarchical shrinkage weights."""

    conversation_effective_n: float | None = Field(default=None, ge=0.0)
    listening_effective_n: float | None = Field(default=None, ge=0.0)
    supply_effective_n: float | None = Field(default=None, ge=0.0)
    conversation_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    listening_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    supply_shrinkage_weight: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )


class SpikeFlagsV2(ApiModel):
    """Nullable stored spike flags when an estimate is unavailable."""

    conversation: bool | None
    listening: bool | None
    supply: bool | None


class OpportunityItemV2(ApiModel):
    """One coverage-aware global or peer-family opportunity."""

    genre: GenreIdentityV2
    week: date
    context: ComparisonContextV2
    estimate_status: str
    opportunity: EstimateBand | None
    discovery_gap: EstimateBand | None
    conversation: EstimateBand | None
    listening: EstimateBand | None
    supply: EstimateBand | None
    diagnostics: OpportunityDiagnosticsV2
    spike_flags: SpikeFlagsV2
    breakout_flag: bool | None


class OpportunityPageV2(ApiModel):
    """Cursor-paginated opportunity results."""

    taxonomy_version: str
    week: date | None
    context: ComparisonContextV2
    items: tuple[OpportunityItemV2, ...]
    page: CursorPageMeta


class TrendAxisV2(ApiModel):
    """Stored z-index and EWMA with their uncertainty bands."""

    index: EstimateBand
    ewma: EstimateBand
    spike: bool


class GenreHistoryPointV2(ApiModel):
    """One precomputed v2 metric week."""

    week: date
    coverage_status: CoverageStatusV2
    estimate_status: str
    conversation: TrendAxisV2 | None
    listening: TrendAxisV2 | None
    supply: TrendAxisV2 | None
    opportunity: EstimateBand | None
    discovery_gap: EstimateBand | None


class ValidationScoreV2(ApiModel):
    """Backtest MASE and empirical interval coverage in one validation group."""

    mase: float | None = Field(default=None, ge=0.0)
    coverage_80: float | None = Field(default=None, ge=0.0, le=1.0)
    score_status: ScoreStatusV2 | None


class NaiveBaselineV2(ApiModel):
    """Persistence forecast retained beside every publishable forecast."""

    prediction_interval_80: EstimateBand
    validation: ValidationScoreV2


class ForecastItemV2(ApiModel):
    """One selected or cold-start taxonomy-v2 forecast."""

    genre: GenreIdentityV2
    origin_week: date | None
    target_week: date | None
    context: ComparisonContextV2
    target_axis: Literal["conversation", "listening"]
    horizon: int = Field(ge=1, le=2)
    forecast_status: ForecastStatusV2
    model: ForecastModelV2 | None
    prediction_interval_80: EstimateBand | None
    genre_validation: ValidationScoreV2 | None
    family_validation: ValidationScoreV2 | None
    naive_baseline: NaiveBaselineV2 | None
    valid_training_weeks: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_forecast_claim(self) -> ForecastItemV2:
        skill_fields = (
            self.model,
            self.prediction_interval_80,
            self.genre_validation,
            self.family_validation,
            self.naive_baseline,
        )
        if self.forecast_status in {"ready", "no_skill"}:
            if any(value is None for value in skill_fields):
                raise ValueError("publishable forecasts require uncertainty and skill")
        elif any(value is not None for value in skill_fields):
            raise ValueError("cold-start forecasts cannot carry a skill claim")
        return self


class ForecastPageV2(ApiModel):
    """Cursor-paginated current forecasts."""

    taxonomy_version: str
    context: ComparisonContextV2
    items: tuple[ForecastItemV2, ...]
    page: CursorPageMeta


class GenreTimeseriesResponseV2(ApiModel):
    """One stable genre's history and current validated forecast statuses."""

    genre: GenreIdentityV2
    context: ComparisonContextV2
    history: tuple[GenreHistoryPointV2, ...]
    forecasts: tuple[ForecastItemV2, ...]


class ConversationReceiptV2(ApiModel):
    """A direct materialized Bluesky post receipt."""

    source: Literal["conversation"] = "conversation"
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


class ListeningReceiptV2(ApiModel):
    """The exact consecutive Last.fm snapshots behind one valid delta."""

    source: Literal["listening"] = "listening"
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
    interval_days: float = Field(gt=0.0)
    listening_window_status: Literal["valid_weekly", "legacy_unvalidated"]
    membership_weight: float = Field(gt=0.0, le=1.0)
    membership_method: str
    membership_confidence: float = Field(ge=0.0, le=1.0)

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)
    _previous_fetched_at_utc = field_validator("previous_fetched_at")(_as_utc)


class SupplyReceiptV2(ApiModel):
    """A direct materialized MusicBrainz release-group receipt."""

    source: Literal["supply"] = "supply"
    release_group_mbid: str
    title: str
    artist_credits: tuple[ArtistCredit, ...]
    first_release_date: date
    types: tuple[str, ...]
    genres: tuple[str, ...]
    fetched_at: datetime
    membership_weight: float = Field(gt=0.0, le=1.0)

    _fetched_at_utc = field_validator("fetched_at")(_as_utc)


EvidenceReceiptV2 = Annotated[
    ConversationReceiptV2 | ListeningReceiptV2 | SupplyReceiptV2,
    Field(discriminator="source"),
]


class EvidencePageV2(ApiModel):
    """One source-specific page of direct receipts."""

    genre: GenreIdentityV2
    week: date
    source: EvidenceSourceV2
    items: tuple[EvidenceReceiptV2, ...]
    page: CursorPageMeta


class AxisModelSkillV2(ApiModel):
    """Selected axis model and the backtest record behind it."""

    model: ForecastModelV2
    forecast_status: Literal["ready", "no_skill"]
    mase: float | None = Field(default=None, ge=0.0)
    coverage_80: float = Field(ge=0.0, le=1.0)


class NextUpItemV2(ApiModel):
    """Precomputed breakout ranking with inherited uncertainty and skill."""

    genre: GenreIdentityV2
    origin_week: date
    target_week: date
    context: ComparisonContextV2
    rank: int = Field(gt=0)
    predicted_opportunity: EstimateBand
    predicted_gain: EstimateBand
    conversation: AxisModelSkillV2
    listening: AxisModelSkillV2
    skill_status: Literal["skill", "no_skill"]


class NextUpPageV2(ApiModel):
    """Cursor-paginated next-up ranking."""

    taxonomy_version: str
    context: ComparisonContextV2
    items: tuple[NextUpItemV2, ...]
    page: CursorPageMeta


class EcosystemPointV2(ApiModel):
    """One global or macro-family ecosystem-health week."""

    taxonomy_version: str
    week: date
    context: ComparisonContextV2
    macro_family_id: str | None
    estimate_status: str
    listening_entropy: EstimateBand | None
    effective_genres: EstimateBand | None
    conversation_hhi: EstimateBand | None
    listening_top_share: EstimateBand | None
    listening_top_share_k: int = Field(ge=0)
    scene_churn_jaccard_4w: EstimateBand | None
    breakout_genre_ids: tuple[str, ...]
    eligible_genres: int = Field(ge=0)


class CreatorBriefV2(ApiModel):
    """A materialized taxonomy-v2 creator brief with forecast validation."""

    genre: GenreIdentityV2
    brief_id: str
    week: date
    context: ComparisonContextV2
    headline: str
    opportunity: EstimateBand
    forecast_direction: EstimateBand
    forecast_model: ForecastModelV2
    backtest_mase: float | None = Field(default=None, ge=0.0)
    backtest_coverage_80: float = Field(ge=0.0, le=1.0)
    rationale: str
    recommended_actions: tuple[str, ...]
    evidence_uris: tuple[str, ...]
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_as_utc)


class CreatorBriefPageV2(ApiModel):
    """Cursor-paginated materialized briefs."""

    taxonomy_version: str
    week: date | None
    context: ComparisonContextV2
    items: tuple[CreatorBriefV2, ...]
    page: CursorPageMeta


class SceneMapPointV2(ApiModel):
    """One precomputed taxonomy-v2 UMAP point."""

    genre: GenreIdentityV2
    as_of_week: date
    context: ComparisonContextV2
    x: float
    y: float
    opportunity: EstimateBand | None
    discovery_gap: EstimateBand | None
    evidence_volume: int = Field(ge=0)


class SceneMapPageV2(ApiModel):
    """Cursor-paginated precomputed scene map."""

    taxonomy_version: str
    as_of_week: date | None
    context: ComparisonContextV2
    items: tuple[SceneMapPointV2, ...]
    page: CursorPageMeta


class CoverageItemV2(ApiModel):
    """One genre-week source-coverage result without zero-filled missingness."""

    genre: GenreIdentityV2
    week: date
    lastfm_tag_available: bool | None
    unique_lastfm_artists: int | None = Field(default=None, ge=0)
    artists_with_consecutive_valid_snapshots: int | None = Field(
        default=None,
        ge=0,
    )
    lastfm_history_weeks: int | None = Field(default=None, ge=0)
    musicbrainz_release_group_count: int | None = Field(default=None, ge=0)
    resolved_bluesky_post_count: int | None = Field(default=None, ge=0)
    resolution_attempt_count: int | None = Field(default=None, ge=0)
    resolution_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    cross_source_overlap_artist_count: int | None = Field(default=None, ge=0)
    cross_source_overlap: float | None = Field(default=None, ge=0.0, le=1.0)
    latest_source_timestamp: datetime | None
    missing_axes: tuple[Literal["conversation", "listening", "supply"], ...]
    stale: bool


class CoveragePageV2(ApiModel):
    """Cursor-paginated coverage and missingness report."""

    taxonomy_version: str
    week: date | None
    items: tuple[CoverageItemV2, ...]
    page: CursorPageMeta
