INSERT INTO mart_.metric_estimates_v2 (
    taxonomy_version,
    week_start,
    scope_type,
    scope_id,
    macro_family_id,
    context,
    metric_name,
    estimate_status,
    estimate,
    ci_low,
    ci_high,
    ewma,
    ewma_ci_low,
    ewma_ci_high,
    spike,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
