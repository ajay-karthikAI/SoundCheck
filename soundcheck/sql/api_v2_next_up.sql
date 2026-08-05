SELECT
    genre_id,
    coverage_status,
    origin_week,
    target_week,
    context,
    rank,
    predicted_opportunity,
    predicted_opportunity_interval_low,
    predicted_opportunity_interval_high,
    predicted_gain,
    gain_interval_low,
    gain_interval_high,
    conversation_model,
    conversation_mase,
    conversation_coverage_80,
    conversation_status,
    listening_model,
    listening_mase,
    listening_coverage_80,
    listening_status,
    skill_status
FROM fcst_.next_up_v2
WHERE
    taxonomy_version = ?
    AND context = ?
    AND (? IS NULL OR macro_family_id = ?)
    AND (? IS NULL OR parent_genre_id = ?)
    AND (? IS NULL OR coverage_status = ?)
ORDER BY rank, genre_id
LIMIT ? OFFSET ?;
