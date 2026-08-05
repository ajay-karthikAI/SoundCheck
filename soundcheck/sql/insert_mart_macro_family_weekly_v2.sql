INSERT INTO mart_.macro_family_weekly_v2 (
    taxonomy_version,
    week_start,
    iso_year,
    iso_week,
    macro_family_id,
    display_name,
    total_genres,
    eligible_genres,
    estimate_status,
    coverage_state_counts_json,
    conversation_score_raw,
    listening_score_raw,
    supply_release_groups_raw,
    conversation_effective_n,
    listening_effective_n,
    supply_effective_n,
    breakout_genres_global,
    breakout_genres_peer,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
