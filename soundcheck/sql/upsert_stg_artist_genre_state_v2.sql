INSERT INTO stg_.artist_genre_resolution_state_v2 (
    artist_key,
    input_fingerprint,
    taxonomy_version,
    resolved_at
)
VALUES (?, ?, ?, ?)
ON CONFLICT (taxonomy_version, artist_key) DO UPDATE SET
    input_fingerprint = excluded.input_fingerprint,
    resolved_at = excluded.resolved_at;
