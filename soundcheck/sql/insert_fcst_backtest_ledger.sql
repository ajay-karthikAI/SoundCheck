INSERT INTO fcst_.backtest_ledger (
    canonical_genre,
    target_axis,
    horizon,
    model_name,
    origin_week,
    target_week,
    training_start_week,
    training_end_week,
    training_weeks,
    actual,
    prediction,
    interval_low,
    interval_high,
    absolute_error,
    covered_80
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
