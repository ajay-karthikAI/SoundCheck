INSERT INTO fcst_.predictions (
    origin_week,
    target_week,
    canonical_genre,
    target_axis,
    horizon,
    model_name,
    is_naive_baseline,
    skill_status,
    prediction,
    interval_low,
    interval_high,
    backtest_mase,
    backtest_coverage_80,
    backtest_origin_count,
    training_start_week,
    training_end_week,
    created_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
