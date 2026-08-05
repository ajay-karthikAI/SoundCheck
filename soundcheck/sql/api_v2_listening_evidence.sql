SELECT
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
    membership_weight,
    membership_method,
    membership_confidence
FROM mart_.listening_evidence_v2
WHERE taxonomy_version = ? AND genre_id = ? AND week_start = ?
ORDER BY artist_key
LIMIT ? OFFSET ?;
