INSERT INTO fcst_.backtest_ledger_v2 (
    taxonomy_version,
    genre_id,
    macro_family_id,
    popularity_tier,
    context,
    target_axis,
    horizon,
    model_name,
    origin_week,
    target_week,
    training_start_week,
    training_end_week,
    training_weeks,
    max_feature_week,
    actual,
    prediction,
    interval_low,
    interval_high,
    absolute_error,
    covered_80
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
