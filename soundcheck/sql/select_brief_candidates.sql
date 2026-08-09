WITH ranked_opportunities AS (
    SELECT
        metric.*,
        ntile(10) OVER (
            ORDER BY metric.opportunity DESC, metric.canonical_genre
        ) AS opportunity_decile
    FROM mart_.genre_weekly_production AS metric
    WHERE
        metric.week_start = ?
        AND metric.opportunity IS NOT NULL
),
supply_history AS (
    SELECT
        current_metric.canonical_genre,
        median(history.supply_release_groups) AS typical_releases,
        min(history.supply_release_groups) AS release_range_low,
        max(history.supply_release_groups) AS release_range_high,
        count(history.week_start) AS history_weeks
    FROM ranked_opportunities AS current_metric
    INNER JOIN mart_.genre_weekly_production AS history
        ON
            history.canonical_genre = current_metric.canonical_genre
            AND history.week_start < current_metric.week_start
    GROUP BY current_metric.canonical_genre
),
selected_axis_forecasts AS (
    SELECT
        origin_week,
        max(target_week) AS target_week,
        canonical_genre,
        max(prediction) FILTER (
            WHERE target_axis = 'conversation'
        ) AS conversation_prediction,
        max(interval_low) FILTER (
            WHERE target_axis = 'conversation'
        ) AS conversation_interval_low,
        max(interval_high) FILTER (
            WHERE target_axis = 'conversation'
        ) AS conversation_interval_high,
        max(prediction) FILTER (
            WHERE target_axis = 'listening'
        ) AS listening_prediction,
        max(interval_low) FILTER (
            WHERE target_axis = 'listening'
        ) AS listening_interval_low,
        max(interval_high) FILTER (
            WHERE target_axis = 'listening'
        ) AS listening_interval_high,
        CASE
            WHEN count(*) FILTER (WHERE skill_status = 'skill') = 2
                THEN 'skill'
            ELSE 'no_skill'
        END AS skill_status
    FROM fcst_.predictions
    WHERE
        horizon = 1
        AND skill_status IN ('skill', 'no_skill')
    GROUP BY origin_week, canonical_genre
    HAVING count(DISTINCT target_axis) = 2
),
opportunity_forecasts AS (
    SELECT
        metric.*,
        forecast.target_week,
        (
            forecast.conversation_prediction
            + forecast.listening_prediction
        ) / 2.0 - metric.supply_index AS predicted_opportunity,
        (
            forecast.conversation_interval_low
            + forecast.listening_interval_low
        ) / 2.0 - metric.supply_index_ci_high AS raw_opportunity_low,
        (
            forecast.conversation_interval_high
            + forecast.listening_interval_high
        ) / 2.0 - metric.supply_index_ci_low AS raw_opportunity_high,
        forecast.skill_status
    FROM ranked_opportunities AS metric
    INNER JOIN selected_axis_forecasts AS forecast
        ON
            forecast.origin_week = metric.week_start
            AND forecast.canonical_genre = metric.canonical_genre
),
brief_forecasts AS (
    SELECT
        opportunity_forecasts.*,
        predicted_opportunity - opportunity AS predicted_gain,
        least(
            predicted_opportunity,
            raw_opportunity_low
        ) AS predicted_opportunity_interval_low,
        greatest(
            predicted_opportunity,
            raw_opportunity_high
        ) AS predicted_opportunity_interval_high
    FROM opportunity_forecasts
)
SELECT
    metric.week_start,
    metric.canonical_genre,
    metric.opportunity,
    metric.opportunity_ci_low,
    metric.opportunity_ci_high,
    metric.conversation_effective_n,
    metric.supply_effective_n,
    metric.supply_release_groups,
    supply.typical_releases,
    supply.release_range_low,
    supply.release_range_high,
    supply.history_weeks,
    metric.target_week,
    metric.predicted_gain,
    least(
        metric.predicted_gain,
        metric.predicted_opportunity_interval_low
            - metric.opportunity_ci_high
    ) AS gain_interval_low,
    greatest(
        metric.predicted_gain,
        metric.predicted_opportunity_interval_high
            - metric.opportunity_ci_low
    ) AS gain_interval_high,
    metric.predicted_opportunity,
    metric.predicted_opportunity_interval_low,
    metric.predicted_opportunity_interval_high,
    metric.skill_status
FROM brief_forecasts AS metric
LEFT JOIN supply_history AS supply
    ON supply.canonical_genre = metric.canonical_genre
WHERE
    metric.opportunity_decile = 1
    AND metric.predicted_gain > 0
    AND metric.predicted_opportunity > 0
ORDER BY metric.opportunity DESC, metric.canonical_genre;
