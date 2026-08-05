INSERT INTO fcst_.model_scores_v2 (
    taxonomy_version,
    validation_scope,
    validation_group_id,
    genre_id,
    macro_family_id,
    popularity_tier,
    context,
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
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
