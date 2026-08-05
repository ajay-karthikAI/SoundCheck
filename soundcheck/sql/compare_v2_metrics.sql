SELECT
    estimates.week_start,
    estimates.scope_id AS genre_id,
    estimates.metric_name,
    estimates.estimate,
    estimates.ci_low,
    estimates.ci_high,
    estimates.estimate_status
FROM mart_.metric_estimates_v2 AS estimates
WHERE
    estimates.taxonomy_version = ?
    AND estimates.scope_type = 'genre'
    AND estimates.context = 'global'
ORDER BY estimates.week_start, estimates.scope_id, estimates.metric_name;
