WITH estimates AS (
    SELECT
        taxonomy_version,
        week_start,
        scope_id AS genre_id,
        context,
        first(estimate_status) AS estimate_status,
        max(estimate) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity,
        max(ci_low) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'opportunity'
        ) AS opportunity_high,
        max(estimate) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap,
        max(ci_low) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'discovery_gap'
        ) AS discovery_gap_high,
        max(estimate) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation,
        max(ci_low) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_high,
        max(estimate) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening,
        max(ci_low) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_high,
        max(estimate) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply,
        max(ci_low) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_high,
        bool_or(spike) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_spike,
        bool_or(spike) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_spike,
        bool_or(spike) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_spike
    FROM mart_.metric_estimates_v2_production
    WHERE
        taxonomy_version = ?
        AND week_start = ?
        AND scope_type = 'genre'
        AND context = ?
    GROUP BY taxonomy_version, week_start, scope_id, context
)
SELECT
    base.genre_id,
    base.week_start,
    base.coverage_state,
    estimate.estimate_status,
    estimate.opportunity,
    estimate.opportunity_low,
    estimate.opportunity_high,
    estimate.discovery_gap,
    estimate.discovery_gap_low,
    estimate.discovery_gap_high,
    estimate.conversation,
    estimate.conversation_low,
    estimate.conversation_high,
    estimate.listening,
    estimate.listening_low,
    estimate.listening_high,
    estimate.supply,
    estimate.supply_low,
    estimate.supply_high,
    base.conversation_effective_n,
    base.listening_effective_n,
    base.supply_effective_n,
    base.conversation_combined_shrinkage_weight,
    base.listening_shrinkage_weight,
    base.supply_combined_shrinkage_weight,
    estimate.conversation_spike,
    estimate.listening_spike,
    estimate.supply_spike,
    CASE ?
        WHEN 'global' THEN base.breakout_global
        ELSE base.breakout_peer_family
    END AS breakout
FROM mart_.genre_weekly_v2_production AS base
LEFT JOIN estimates AS estimate
    ON estimate.taxonomy_version = base.taxonomy_version
    AND estimate.week_start = base.week_start
    AND estimate.genre_id = base.genre_id
WHERE
    base.taxonomy_version = ?
    AND base.week_start = ?
    AND base.week_start < CAST(date_trunc('week', current_timestamp) AS DATE)
    AND (? IS NULL OR base.macro_family_id = ?)
    AND (? IS NULL OR base.parent_genre_id = ?)
    AND (? IS NULL OR base.coverage_state = ?)
ORDER BY estimate.opportunity DESC NULLS LAST, base.genre_id
LIMIT ? OFFSET ?;
