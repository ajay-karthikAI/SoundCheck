WITH legacy_opportunity AS (
    SELECT taxonomy_version, week_start, scope_id, estimate
    FROM mart_.metric_estimates_v2
    WHERE
        taxonomy_version = ?
        AND scope_type = 'genre'
        AND context = 'global'
        AND metric_name = 'opportunity'
        AND estimate IS NOT NULL
),
legacy_gap AS (
    SELECT taxonomy_version, week_start, scope_id, estimate
    FROM mart_.metric_estimates_v2
    WHERE
        taxonomy_version = ?
        AND scope_type = 'genre'
        AND context = 'global'
        AND metric_name = 'discovery_gap'
),
corrected AS (
    SELECT week_start, scope_id, estimate
    FROM mart_.metric_estimates_v2_versioned
    WHERE
        derivation_version = ?
        AND taxonomy_version = ?
        AND scope_type = 'genre'
        AND context = 'global'
        AND metric_name = 'opportunity'
)
INSERT INTO mart_.metric_row_withdrawals
SELECT
    'v2',
    legacy.taxonomy_version,
    ?,
    legacy.week_start,
    legacy.scope_id,
    legacy.estimate,
    gap.estimate,
    'listening_window_not_valid_weekly'
FROM legacy_opportunity AS legacy
LEFT JOIN legacy_gap AS gap USING (taxonomy_version, week_start, scope_id)
LEFT JOIN corrected USING (week_start, scope_id)
WHERE corrected.estimate IS NULL;
