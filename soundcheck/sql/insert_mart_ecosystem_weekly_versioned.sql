INSERT INTO mart_.ecosystem_weekly_versioned (
    derivation_version,
    week_start,
    iso_year,
    iso_week,
    shannon_listening_entropy,
    shannon_listening_entropy_ci_low,
    shannon_listening_entropy_ci_high,
    effective_genres,
    effective_genres_ci_low,
    effective_genres_ci_high,
    conversation_hhi,
    conversation_hhi_ci_low,
    conversation_hhi_ci_high,
    listening_top10_share,
    listening_top10_share_ci_low,
    listening_top10_share_ci_high,
    scene_churn_jaccard_4w,
    scene_churn_jaccard_4w_ci_low,
    scene_churn_jaccard_4w_ci_high,
    breakout_genres,
    canonical_genre_count,
    listening_observed_genres,
    opportunity_observed_genres,
    computed_at
)
VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);
