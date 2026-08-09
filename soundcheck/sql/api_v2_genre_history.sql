WITH recent_weeks AS (
    SELECT week_start
    FROM mart_.genre_weekly_v2_production
    WHERE taxonomy_version = ? AND genre_id = ?
    ORDER BY week_start DESC
    LIMIT ?
),
estimates AS (
    SELECT
        week_start,
        first(estimate_status) AS estimate_status,
        max(estimate) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation,
        max(ci_low) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_high,
        max(ewma) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_ewma,
        max(ewma_ci_low) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_ewma_low,
        max(ewma_ci_high) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_ewma_high,
        bool_or(spike) FILTER (
            WHERE metric_name = 'conversation'
        ) AS conversation_spike,
        max(estimate) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening,
        max(ci_low) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_high,
        max(ewma) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_ewma,
        max(ewma_ci_low) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_ewma_low,
        max(ewma_ci_high) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_ewma_high,
        bool_or(spike) FILTER (
            WHERE metric_name = 'listening'
        ) AS listening_spike,
        max(estimate) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply,
        max(ci_low) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_low,
        max(ci_high) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_high,
        max(ewma) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_ewma,
        max(ewma_ci_low) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_ewma_low,
        max(ewma_ci_high) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_ewma_high,
        bool_or(spike) FILTER (
            WHERE metric_name = 'supply'
        ) AS supply_spike,
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
        ) AS discovery_gap_high
    FROM mart_.metric_estimates_v2_production
    WHERE
        taxonomy_version = ?
        AND scope_type = 'genre'
        AND scope_id = ?
        AND context = ?
        AND week_start IN (SELECT week_start FROM recent_weeks)
    GROUP BY week_start
)
SELECT
    base.week_start,
    base.coverage_state,
    coalesce(estimate.estimate_status, base.estimate_status),
    estimate.conversation,
    estimate.conversation_low,
    estimate.conversation_high,
    estimate.conversation_ewma,
    estimate.conversation_ewma_low,
    estimate.conversation_ewma_high,
    estimate.conversation_spike,
    estimate.listening,
    estimate.listening_low,
    estimate.listening_high,
    estimate.listening_ewma,
    estimate.listening_ewma_low,
    estimate.listening_ewma_high,
    estimate.listening_spike,
    estimate.supply,
    estimate.supply_low,
    estimate.supply_high,
    estimate.supply_ewma,
    estimate.supply_ewma_low,
    estimate.supply_ewma_high,
    estimate.supply_spike,
    estimate.opportunity,
    estimate.opportunity_low,
    estimate.opportunity_high,
    estimate.discovery_gap,
    estimate.discovery_gap_low,
    estimate.discovery_gap_high
FROM mart_.genre_weekly_v2_production AS base
JOIN recent_weeks USING (week_start)
LEFT JOIN estimates AS estimate USING (week_start)
WHERE base.taxonomy_version = ? AND base.genre_id = ?
ORDER BY base.week_start;
