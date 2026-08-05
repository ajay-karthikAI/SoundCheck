SELECT
    artist_key,
    artist_name,
    artist_mbid,
    playcount_delta,
    listeners_delta,
    fetched_at
FROM mart_.listening_evidence
WHERE
    lower(canonical_genre) = lower(?)
    AND week_start = ?
ORDER BY weighted_delta DESC, artist_key
LIMIT ?;
