SELECT
    genre_id,
    macro_family_id,
    context,
    target_axis,
    horizon,
    forecast_status,
    model_name,
    prediction,
    interval_low,
    interval_high,
    backtest_mase,
    backtest_coverage_80,
    family_backtest_mase,
    family_backtest_coverage_80,
    naive_prediction,
    naive_interval_low,
    naive_interval_high,
    valid_training_weeks,
    target_week
FROM fcst_.predictions_v2
WHERE taxonomy_version = ?
ORDER BY genre_id, context, target_axis, horizon;
