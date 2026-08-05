INSERT INTO fcst_.model_scores (
    canonical_genre,
    target_axis,
    horizon,
    model_name,
    backtest_start_week,
    backtest_end_week,
    origin_count,
    mae,
    naive_mae,
    mase,
    interval_coverage_80,
    mean_interval_width,
    score_status,
    evaluated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
