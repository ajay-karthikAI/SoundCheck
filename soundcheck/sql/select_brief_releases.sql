SELECT
    release_group_mbid,
    title
FROM mart_.supply_evidence
WHERE
    week_start = ?
    AND canonical_genre = ?
ORDER BY first_release_date DESC, title, release_group_mbid
LIMIT ?;
