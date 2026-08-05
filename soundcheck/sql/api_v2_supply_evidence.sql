SELECT
    release_group_mbid,
    title,
    artist_credits,
    first_release_date,
    types,
    genres,
    fetched_at,
    membership_weight
FROM mart_.supply_evidence_v2
WHERE taxonomy_version = ? AND genre_id = ? AND week_start = ?
ORDER BY release_group_mbid
LIMIT ? OFFSET ?;
