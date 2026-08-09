SET TimeZone = 'UTC';

WITH contexts(context) AS (
    VALUES ('global'), ('peer_family')
)
SELECT
    base.taxonomy_version,
    base.week_start,
    base.genre_id,
    base.display_name,
    base.macro_family_id,
    base.parent_genre_id,
    coalesce(coverage.taxonomy_status, 'candidate') AS taxonomy_status,
    base.coverage_state,
    base.estimate_eligible,
    contexts.context,
    max(estimate.estimate) FILTER (
        WHERE estimate.metric_name = 'conversation'
    ) AS conversation,
    max(estimate.estimate) FILTER (
        WHERE estimate.metric_name = 'listening'
    ) AS listening,
    max(estimate.estimate) FILTER (
        WHERE estimate.metric_name = 'supply'
    ) AS supply,
    max(estimate.estimate) FILTER (
        WHERE estimate.metric_name = 'discovery_gap'
    ) AS discovery_gap,
    max(estimate.estimate) FILTER (
        WHERE estimate.metric_name = 'opportunity'
    ) AS opportunity,
    max(estimate.ewma) FILTER (
        WHERE estimate.metric_name = 'conversation'
    ) AS conversation_ewma,
    max(estimate.ewma) FILTER (
        WHERE estimate.metric_name = 'listening'
    ) AS listening_ewma,
    max(estimate.ewma) FILTER (
        WHERE estimate.metric_name = 'supply'
    ) AS supply_ewma,
    bool_or(estimate.spike) FILTER (
        WHERE estimate.metric_name = 'conversation'
    ) AS conversation_spike,
    bool_or(estimate.spike) FILTER (
        WHERE estimate.metric_name = 'listening'
    ) AS listening_spike,
    bool_or(estimate.spike) FILTER (
        WHERE estimate.metric_name = 'supply'
    ) AS supply_spike,
    base.conversation_effective_n,
    base.listening_effective_n
FROM mart_.genre_weekly_v2_production AS base
CROSS JOIN contexts
LEFT JOIN mart_.genre_coverage_v2 AS coverage
    ON coverage.taxonomy_version = base.taxonomy_version
    AND coverage.week_start = base.week_start
    AND coverage.genre_id = base.genre_id
LEFT JOIN mart_.metric_estimates_v2_production AS estimate
    ON estimate.taxonomy_version = base.taxonomy_version
    AND estimate.week_start = base.week_start
    AND estimate.scope_type = 'genre'
    AND estimate.scope_id = base.genre_id
    AND estimate.context = contexts.context
WHERE base.taxonomy_version = ?
GROUP BY ALL
ORDER BY
    base.week_start,
    base.genre_id,
    contexts.context;
