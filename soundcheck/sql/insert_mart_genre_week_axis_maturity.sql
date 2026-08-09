INSERT INTO mart_.genre_week_axis_maturity (
    artifact_family,
    taxonomy_version,
    week_start,
    genre_id,
    conversation_maturity,
    listening_maturity,
    supply_maturity,
    decision_ready,
    conversation_post_count,
    mature_conversation_post_count,
    valid_listening_artist_count,
    supply_release_group_count,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
