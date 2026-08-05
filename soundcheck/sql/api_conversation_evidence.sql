SELECT
    post_uri,
    did,
    created_at,
    text,
    like_count,
    repost_count,
    reply_count,
    artist_name_raw,
    resolution_method,
    resolution_score,
    join_key_type
FROM mart_.conversation_evidence
WHERE
    lower(canonical_genre) = lower(?)
    AND week_start = ?
ORDER BY weighted_score DESC, post_uri
LIMIT ?;
