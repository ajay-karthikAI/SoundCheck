INSERT INTO mart_.ecosystem_weekly_v2 (
    taxonomy_version,
    week_start,
    iso_year,
    iso_week,
    scope_type,
    scope_id,
    estimate_status,
    listening_entropy,
    listening_entropy_ci_low,
    listening_entropy_ci_high,
    effective_genres,
    effective_genres_ci_low,
    effective_genres_ci_high,
    conversation_hhi,
    conversation_hhi_ci_low,
    conversation_hhi_ci_high,
    listening_top_share,
    listening_top_share_ci_low,
    listening_top_share_ci_high,
    listening_top_share_k,
    churn_jaccard_4w,
    churn_jaccard_4w_ci_low,
    churn_jaccard_4w_ci_high,
    breakout_genres,
    eligible_genres,
    computed_at
)
VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);
