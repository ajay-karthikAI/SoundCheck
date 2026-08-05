INSERT INTO fcst_.next_up (
    origin_week,
    target_week,
    canonical_genre,
    rank,
    predicted_opportunity,
    predicted_opportunity_interval_low,
    predicted_opportunity_interval_high,
    predicted_gain,
    gain_interval_low,
    gain_interval_high,
    conversation_model,
    listening_model,
    conversation_mase,
    listening_mase,
    skill_status,
    breakout_evidence_week,
    created_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
