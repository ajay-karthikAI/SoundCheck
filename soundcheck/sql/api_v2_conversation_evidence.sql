SELECT
    post_uri,
    did,
    created_at,
    text,
    likes,
    reposts,
    replies,
    artist_name_raw,
    resolution_method,
    resolution_score,
    join_key_type,
    membership_weight,
    membership_method,
    membership_confidence
FROM mart_.conversation_evidence_v2
WHERE taxonomy_version = ? AND genre_id = ? AND week_start = ?
ORDER BY post_uri
LIMIT ? OFFSET ?;
