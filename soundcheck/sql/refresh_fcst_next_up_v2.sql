INSERT INTO fcst_.next_up_v2 (
    taxonomy_version,
    origin_week,
    target_week,
    genre_id,
    display_name,
    macro_family_id,
    parent_genre_id,
    coverage_status,
    context,
    rank,
    predicted_opportunity,
    predicted_opportunity_interval_low,
    predicted_opportunity_interval_high,
    predicted_gain,
    gain_interval_low,
    gain_interval_high,
    conversation_model,
    conversation_mase,
    conversation_coverage_80,
    conversation_status,
    listening_model,
    listening_mase,
    listening_coverage_80,
    listening_status,
    skill_status,
    created_at
)
WITH current_metrics AS (
    SELECT
        base.taxonomy_version,
        base.week_start,
        base.genre_id,
        base.display_name,
        base.macro_family_id,
        base.parent_genre_id,
        base.coverage_state,
        estimate.context,
        max(estimate.estimate) FILTER (
            WHERE estimate.metric_name = 'supply'
        ) AS supply,
        max(estimate.ci_low) FILTER (
            WHERE estimate.metric_name = 'supply'
        ) AS supply_low,
        max(estimate.ci_high) FILTER (
            WHERE estimate.metric_name = 'supply'
        ) AS supply_high,
        max(estimate.estimate) FILTER (
            WHERE estimate.metric_name = 'opportunity'
        ) AS opportunity,
        max(estimate.ci_low) FILTER (
            WHERE estimate.metric_name = 'opportunity'
        ) AS opportunity_low,
        max(estimate.ci_high) FILTER (
            WHERE estimate.metric_name = 'opportunity'
        ) AS opportunity_high,
        CASE estimate.context
            WHEN 'global' THEN base.breakout_global
            ELSE base.breakout_peer_family
        END AS breakout
    FROM mart_.genre_weekly_v2 AS base
    JOIN mart_.metric_estimates_v2 AS estimate
        ON estimate.taxonomy_version = base.taxonomy_version
        AND estimate.week_start = base.week_start
        AND estimate.scope_type = 'genre'
        AND estimate.scope_id = base.genre_id
    WHERE base.taxonomy_version = ?
    GROUP BY ALL
),
paired AS (
    SELECT
        conversation.taxonomy_version,
        conversation.origin_week,
        conversation.target_week,
        metric.genre_id,
        metric.display_name,
        metric.macro_family_id,
        metric.parent_genre_id,
        metric.coverage_state,
        conversation.context,
        (
            conversation.prediction + listening.prediction
        ) / 2.0 - metric.supply AS predicted_opportunity,
        (
            conversation.interval_low + listening.interval_low
        ) / 2.0 - metric.supply_high AS predicted_opportunity_low,
        (
            conversation.interval_high + listening.interval_high
        ) / 2.0 - metric.supply_low AS predicted_opportunity_high,
        (
            conversation.prediction + listening.prediction
        ) / 2.0 - metric.supply - metric.opportunity AS predicted_gain,
        (
            conversation.interval_low + listening.interval_low
        ) / 2.0 - metric.supply_high
            - metric.opportunity_high AS gain_low,
        (
            conversation.interval_high + listening.interval_high
        ) / 2.0 - metric.supply_low
            - metric.opportunity_low AS gain_high,
        conversation.model_name AS conversation_model,
        conversation.backtest_mase AS conversation_mase,
        conversation.backtest_coverage_80 AS conversation_coverage,
        conversation.forecast_status AS conversation_status,
        listening.model_name AS listening_model,
        listening.backtest_mase AS listening_mase,
        listening.backtest_coverage_80 AS listening_coverage,
        listening.forecast_status AS listening_status,
        conversation.created_at
    FROM fcst_.predictions_v2 AS conversation
    JOIN fcst_.predictions_v2 AS listening
        ON listening.taxonomy_version = conversation.taxonomy_version
        AND listening.origin_week = conversation.origin_week
        AND listening.target_week = conversation.target_week
        AND listening.genre_id = conversation.genre_id
        AND listening.context = conversation.context
        AND listening.horizon = conversation.horizon
        AND listening.target_axis = 'listening'
    JOIN current_metrics AS metric
        ON metric.taxonomy_version = conversation.taxonomy_version
        AND metric.week_start = conversation.origin_week
        AND metric.genre_id = conversation.genre_id
        AND metric.context = conversation.context
    WHERE
        conversation.taxonomy_version = ?
        AND conversation.target_axis = 'conversation'
        AND conversation.horizon = 1
        AND conversation.forecast_status IN ('ready', 'no_skill')
        AND listening.forecast_status IN ('ready', 'no_skill')
        AND metric.breakout
        AND metric.supply IS NOT NULL
        AND metric.opportunity IS NOT NULL
),
ranked AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY taxonomy_version, context, origin_week
            ORDER BY predicted_gain DESC, genre_id
        ) AS opportunity_rank
    FROM paired
)
SELECT
    taxonomy_version,
    origin_week,
    target_week,
    genre_id,
    display_name,
    macro_family_id,
    parent_genre_id,
    coverage_state,
    context,
    opportunity_rank,
    predicted_opportunity,
    least(predicted_opportunity_low, predicted_opportunity),
    greatest(predicted_opportunity_high, predicted_opportunity),
    predicted_gain,
    least(gain_low, predicted_gain),
    greatest(gain_high, predicted_gain),
    conversation_model,
    conversation_mase,
    conversation_coverage,
    conversation_status,
    listening_model,
    listening_mase,
    listening_coverage,
    listening_status,
    CASE
        WHEN
            conversation_status = 'ready'
            AND listening_status = 'ready'
        THEN 'skill'
        ELSE 'no_skill'
    END,
    created_at
FROM ranked;
