WITH coordinates AS (
    SELECT taxonomy_version, genre_id, context, x, y
    FROM mart_.scene_map_v2
    WHERE taxonomy_version = ? AND context = ?
    QUALIFY row_number() OVER (
        PARTITION BY taxonomy_version, genre_id, context
        ORDER BY as_of_week DESC
    ) = 1
),
estimates AS (
    SELECT
        taxonomy_version,
        week_start,
        scope_id AS genre_id,
        context,
        max(estimate) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity,
        max(ci_low) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity_ci_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity_ci_high,
        max(estimate) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap,
        max(ci_low) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap_ci_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap_ci_high
    FROM mart_.metric_estimates_v2_production
    WHERE
        taxonomy_version = ?
        AND week_start = ?
        AND context = ?
        AND scope_type = 'genre'
    GROUP BY taxonomy_version, week_start, scope_id, context
)
SELECT
    base.genre_id,
    base.coverage_state,
    base.week_start AS as_of_week,
    estimates.context,
    coordinates.x,
    coordinates.y,
    estimates.opportunity,
    estimates.opportunity_ci_low,
    estimates.opportunity_ci_high,
    estimates.discovery_gap,
    estimates.discovery_gap_ci_low,
    estimates.discovery_gap_ci_high,
    len(base.conversation_post_uris)
        + len(base.listening_artist_keys)
        + len(base.supply_release_group_mbids) AS evidence_volume
FROM mart_.genre_weekly_v2_production AS base
INNER JOIN estimates USING (taxonomy_version, week_start, genre_id)
INNER JOIN coordinates USING (taxonomy_version, genre_id)
WHERE
    base.taxonomy_version = ?
    AND base.week_start = ?
    AND base.week_start < CAST(date_trunc('week', current_timestamp) AS DATE)
    AND (? IS NULL OR base.macro_family_id = ?)
    AND (? IS NULL OR base.parent_genre_id = ?)
    AND (? IS NULL OR base.coverage_state = ?)
ORDER BY base.genre_id
LIMIT ? OFFSET ?;
