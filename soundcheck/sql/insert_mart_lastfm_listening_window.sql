INSERT INTO mart_.lastfm_listening_windows (
    artifact_family,
    taxonomy_version,
    derivation_version,
    week_start,
    genre_id,
    macro_family_id,
    artist_key,
    artist_name,
    artist_mbid,
    membership_weight,
    playcount,
    listeners,
    previous_playcount,
    previous_listeners,
    previous_fetched_at,
    fetched_at,
    interval_days,
    observations_append_only,
    listening_window_status,
    membership_method,
    membership_confidence
)
VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);
