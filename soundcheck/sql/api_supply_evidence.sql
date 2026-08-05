SELECT
    release_group_mbid,
    title,
    artist_credits,
    first_release_date,
    types,
    genres
FROM mart_.supply_evidence
WHERE
    lower(canonical_genre) = lower(?)
    AND week_start = ?
ORDER BY first_release_date DESC, release_group_mbid
LIMIT ?;
