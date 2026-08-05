SELECT
    post_uri,
    did,
    text,
    weighted_score
FROM mart_.conversation_evidence
WHERE
    week_start = ?
    AND canonical_genre = ?
ORDER BY weighted_score DESC, created_at DESC, post_uri
LIMIT 1;
