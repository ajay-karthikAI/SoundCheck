INSERT INTO mart_.listening_evidence_v2 (
    taxonomy_version,
    week_start,
    genre_id,
    macro_family_id,
    artist_key,
    artist_name,
    artist_mbid,
    playcount,
    listeners,
    previous_playcount,
    previous_listeners,
    playcount_delta,
    listeners_delta,
    fetched_at,
    previous_fetched_at,
    interval_days,
    listening_window_status,
    membership_weight,
    membership_method,
    membership_confidence
)
VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);
