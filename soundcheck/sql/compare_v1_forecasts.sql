SELECT
    canonical_genre,
    target_axis,
    horizon,
    model_name,
    is_naive_baseline,
    skill_status,
    backtest_mase,
    backtest_coverage_80,
    target_week
FROM fcst_.predictions
ORDER BY canonical_genre, target_axis, horizon, model_name;
