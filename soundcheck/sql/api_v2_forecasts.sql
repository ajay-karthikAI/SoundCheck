WITH latest_genres AS (
    SELECT
        taxonomy_version,
        genre_id,
        parent_genre_id,
        coverage_state
    FROM mart_.genre_weekly_v2_production
    WHERE taxonomy_version = ?
    QUALIFY row_number() OVER (
        PARTITION BY taxonomy_version, genre_id
        ORDER BY week_start DESC
    ) = 1
)
SELECT
    prediction.genre_id,
    genre.coverage_state,
    prediction.origin_week,
    prediction.target_week,
    prediction.context,
    prediction.target_axis,
    prediction.horizon,
    prediction.forecast_status,
    prediction.model_name,
    prediction.prediction,
    prediction.interval_low,
    prediction.interval_high,
    prediction.backtest_mase,
    prediction.backtest_coverage_80,
    prediction.backtest_score_status,
    prediction.family_backtest_mase,
    prediction.family_backtest_coverage_80,
    prediction.family_backtest_score_status,
    prediction.naive_prediction,
    prediction.naive_interval_low,
    prediction.naive_interval_high,
    prediction.naive_backtest_mase,
    prediction.naive_backtest_coverage_80,
    prediction.naive_backtest_score_status,
    prediction.valid_training_weeks
FROM fcst_.predictions_v2 AS prediction
LEFT JOIN latest_genres AS genre
    ON genre.taxonomy_version = prediction.taxonomy_version
    AND genre.genre_id = prediction.genre_id
WHERE
    prediction.taxonomy_version = ?
    AND prediction.context = ?
    AND (? IS NULL OR prediction.macro_family_id = ?)
    AND (? IS NULL OR genre.parent_genre_id = ?)
    AND (? IS NULL OR genre.coverage_state = ?)
    AND (? IS NULL OR prediction.genre_id = ?)
ORDER BY
    prediction.target_week NULLS LAST,
    prediction.genre_id,
    prediction.target_axis,
    prediction.horizon
LIMIT ? OFFSET ?;
