SELECT
    artist_key,
    artist_name,
    artist_mbid,
    playcount_delta,
    listeners_delta,
    weighted_delta
FROM mart_.listening_evidence
WHERE
    week_start = ?
    AND canonical_genre = ?
    AND weighted_delta > 0
ORDER BY
    weighted_delta DESC,
    listeners_delta DESC,
    artist_name
LIMIT ?;
