SELECT
    target_week,
    target_axis,
    horizon,
    model_name,
    skill_status,
    prediction,
    interval_low,
    interval_high,
    backtest_mase,
    backtest_coverage_80,
    backtest_origin_count
FROM fcst_.predictions
WHERE
    lower(canonical_genre) = lower(?)
    AND skill_status IN ('skill', 'no_skill')
ORDER BY target_week, target_axis;
