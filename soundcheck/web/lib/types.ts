export type EstimateBand = {
  value: number;
  lower: number;
  upper: number;
};

export type ApiError = {
  detail: {
    code: string;
    message: string;
  };
};

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; message: string };

export type ComparisonContext = "global" | "peer_family";

export type CoverageStatus =
  | "ready"
  | "collecting_history"
  | "insufficient_listening"
  | "insufficient_conversation"
  | "insufficient_supply"
  | "insufficient_resolution"
  | "unsupported"
  | "not_observed";

export type TaxonomyStatus = "enabled" | "candidate" | "rejected";

export type ForecastStatus =
  | "ready"
  | "no_skill"
  | "insufficient_history"
  | "insufficient_evidence";

export type ForecastModel =
  | "naive"
  | "seasonal_naive"
  | "ets"
  | "lightgbm";

export type CursorPage = {
  next_cursor: string | null;
  has_more: boolean;
};

export type GenreIdentity = {
  genre_id: string;
  slug: string;
  display_name: string;
  macro_family_id: string;
  macro_family_name: string;
  parent_genre_id: string | null;
  taxonomy_version: string;
  taxonomy_status: TaxonomyStatus;
  coverage_status: CoverageStatus;
};

export type MacroFamily = {
  macro_family_id: string;
  display_name: string;
  slug: string;
};

export type GenreCatalogPage = {
  items: GenreIdentity[];
  page: CursorPage;
};

export type TaxonomyResponse = {
  taxonomy_version: string;
  default_genre_id: string;
  other_genre_id: string;
  unresolved_genre_id: string;
  genres: GenreCatalogPage;
};

export type MacroFamilyPage = {
  taxonomy_version: string;
  items: MacroFamily[];
  page: CursorPage;
};

export type OpportunityItem = {
  genre: GenreIdentity;
  week: string;
  context: ComparisonContext;
  estimate_status: string;
  opportunity: EstimateBand | null;
  discovery_gap: EstimateBand | null;
  conversation: EstimateBand | null;
  listening: EstimateBand | null;
  supply: EstimateBand | null;
  diagnostics: {
    conversation_effective_n: number | null;
    listening_effective_n: number | null;
    supply_effective_n: number | null;
    conversation_shrinkage_weight: number | null;
    listening_shrinkage_weight: number | null;
    supply_shrinkage_weight: number | null;
  };
  spike_flags: {
    conversation: boolean | null;
    listening: boolean | null;
    supply: boolean | null;
  };
  breakout_flag: boolean | null;
};

export type OpportunityPage = {
  taxonomy_version: string;
  week: string | null;
  context: ComparisonContext;
  items: OpportunityItem[];
  page: CursorPage;
};

export type TrendAxis = {
  index: EstimateBand;
  ewma: EstimateBand;
  spike: boolean;
};

export type GenreHistoryPoint = {
  week: string;
  coverage_status: CoverageStatus;
  estimate_status: string;
  conversation: TrendAxis | null;
  listening: TrendAxis | null;
  supply: TrendAxis | null;
  opportunity: EstimateBand | null;
  discovery_gap: EstimateBand | null;
};

export type ValidationScore = {
  mase: number | null;
  coverage_80: number | null;
  score_status: string | null;
};

export type ForecastItem = {
  genre: GenreIdentity;
  origin_week: string | null;
  target_week: string | null;
  context: ComparisonContext;
  target_axis: "conversation" | "listening";
  horizon: 1 | 2;
  forecast_status: ForecastStatus;
  model: ForecastModel | null;
  prediction_interval_80: EstimateBand | null;
  genre_validation: ValidationScore | null;
  family_validation: ValidationScore | null;
  naive_baseline: {
    prediction_interval_80: EstimateBand;
    validation: ValidationScore;
  } | null;
  valid_training_weeks: number;
};

export type ForecastPage = {
  taxonomy_version: string;
  context: ComparisonContext;
  items: ForecastItem[];
  page: CursorPage;
};

export type GenreTimeseries = {
  genre: GenreIdentity;
  context: ComparisonContext;
  history: GenreHistoryPoint[];
  forecasts: ForecastItem[];
};

export type ArtistCredit = {
  credit_name: string;
  artist_name: string;
  mbid: string | null;
  join_phrase: string;
};

export type ConversationReceipt = {
  source: "conversation";
  post_uri: string;
  did: string;
  created_at: string;
  text: string;
  likes: number;
  reposts: number;
  replies: number;
  artist_name_raw: string;
  resolution_method: string;
  resolution_score: number;
  join_key_type: string;
  membership_weight: number;
  membership_method: string;
  membership_confidence: number;
};

export type ListeningReceipt = {
  source: "listening";
  artist_key: string;
  artist_name: string;
  artist_mbid: string | null;
  playcount: number;
  listeners: number;
  previous_playcount: number;
  previous_listeners: number;
  playcount_delta: number;
  listeners_delta: number;
  fetched_at: string;
  previous_fetched_at: string;
  interval_days: number;
  listening_window_status: "valid_weekly" | "legacy_unvalidated";
  membership_weight: number;
  membership_method: string;
  membership_confidence: number;
};

export type SupplyReceipt = {
  source: "supply";
  release_group_mbid: string;
  title: string;
  artist_credits: ArtistCredit[];
  first_release_date: string;
  types: string[];
  genres: string[];
  fetched_at: string;
  membership_weight: number;
};

export type EvidenceSource = "conversation" | "listening" | "supply";
export type EvidenceReceipt =
  | ConversationReceipt
  | ListeningReceipt
  | SupplyReceipt;

export type EvidencePage = {
  genre: GenreIdentity;
  week: string;
  source: EvidenceSource;
  items: EvidenceReceipt[];
  page: CursorPage;
};

export type GenreEvidenceBundle = {
  genre: GenreIdentity;
  week: string;
  conversation: ConversationReceipt[];
  listening: ListeningReceipt[];
  supply: SupplyReceipt[];
  unavailable_sources: EvidenceSource[];
};

export type AxisModelSkill = {
  model: ForecastModel;
  forecast_status: "ready" | "no_skill";
  mase: number | null;
  coverage_80: number;
};

export type NextUpItem = {
  genre: GenreIdentity;
  origin_week: string;
  target_week: string;
  context: ComparisonContext;
  rank: number;
  predicted_opportunity: EstimateBand;
  predicted_gain: EstimateBand;
  conversation: AxisModelSkill;
  listening: AxisModelSkill;
  skill_status: "skill" | "no_skill";
};

export type NextUpPage = {
  taxonomy_version: string;
  context: ComparisonContext;
  items: NextUpItem[];
  page: CursorPage;
};

export type EcosystemPoint = {
  taxonomy_version: string;
  week: string;
  context: ComparisonContext;
  macro_family_id: string | null;
  estimate_status: string;
  listening_entropy: EstimateBand | null;
  effective_genres: EstimateBand | null;
  conversation_hhi: EstimateBand | null;
  listening_top_share: EstimateBand | null;
  listening_top_share_k: number;
  scene_churn_jaccard_4w: EstimateBand | null;
  breakout_genre_ids: string[];
  eligible_genres: number;
};

export type CreatorBrief = {
  genre: GenreIdentity;
  brief_id: string;
  week: string;
  context: ComparisonContext;
  headline: string;
  opportunity: EstimateBand;
  forecast_direction: EstimateBand;
  forecast_model: ForecastModel;
  backtest_mase: number | null;
  backtest_coverage_80: number;
  rationale: string;
  recommended_actions: string[];
  evidence_uris: string[];
  created_at: string;
};

export type CreatorBriefPage = {
  taxonomy_version: string;
  week: string | null;
  context: ComparisonContext;
  items: CreatorBrief[];
  page: CursorPage;
};

export type SceneMapPoint = {
  genre: GenreIdentity;
  as_of_week: string;
  context: ComparisonContext;
  x: number;
  y: number;
  opportunity: EstimateBand | null;
  discovery_gap: EstimateBand | null;
  evidence_volume: number;
};

export type SceneMapPage = {
  taxonomy_version: string;
  as_of_week: string | null;
  context: ComparisonContext;
  items: SceneMapPoint[];
  page: CursorPage;
};

export type CoverageItem = {
  genre: GenreIdentity;
  week: string;
  lastfm_tag_available: boolean | null;
  unique_lastfm_artists: number | null;
  artists_with_consecutive_valid_snapshots: number | null;
  lastfm_history_weeks: number | null;
  musicbrainz_release_group_count: number | null;
  resolved_bluesky_post_count: number | null;
  resolution_attempt_count: number | null;
  resolution_rate: number | null;
  cross_source_overlap_artist_count: number | null;
  cross_source_overlap: number | null;
  latest_source_timestamp: string | null;
  missing_axes: Array<"conversation" | "listening" | "supply">;
  stale: boolean;
};

export type CoveragePage = {
  taxonomy_version: string;
  week: string | null;
  items: CoverageItem[];
  page: CursorPage;
};

export type ScopeSelection = {
  macroFamilyId?: string;
  context: ComparisonContext;
  week?: string;
};

export function hasOpportunity(
  item: OpportunityItem,
): item is OpportunityItem & {
  opportunity: EstimateBand;
  discovery_gap: EstimateBand;
  conversation: EstimateBand;
  listening: EstimateBand;
  supply: EstimateBand;
} {
  return Boolean(
    item.opportunity &&
      item.discovery_gap &&
      item.conversation &&
      item.listening &&
      item.supply,
  );
}
