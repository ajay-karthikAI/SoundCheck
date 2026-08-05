SELECT
    artist_key,
    input_fingerprint
FROM stg_.artist_genre_resolution_state_v2
WHERE taxonomy_version = ?
ORDER BY artist_key;
