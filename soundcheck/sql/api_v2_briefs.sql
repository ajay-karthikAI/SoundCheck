SELECT
    genre_id,
    coverage_status,
    brief_id,
    week_start,
    context,
    headline,
    opportunity,
    opportunity_ci_low,
    opportunity_ci_high,
    forecast_direction,
    forecast_interval_low,
    forecast_interval_high,
    forecast_model,
    backtest_mase,
    backtest_coverage_80,
    rationale,
    recommended_actions,
    evidence_uris,
    created_at
FROM mart_.briefs_v2
WHERE
    taxonomy_version = ?
    AND week_start = ?
    AND context = ?
    AND (? IS NULL OR macro_family_id = ?)
    AND (? IS NULL OR parent_genre_id = ?)
    AND (? IS NULL OR coverage_status = ?)
ORDER BY opportunity DESC, genre_id
LIMIT ? OFFSET ?;
