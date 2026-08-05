INSERT INTO stg_.post_artist_links (
    post_uri,
    artist_mbid,
    artist_name_raw,
    method,
    score,
    join_key_type,
    resolved_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (post_uri, artist_name_raw) DO UPDATE SET
    artist_mbid = CASE
        WHEN excluded.join_key_type = 'mbid'
            THEN excluded.artist_mbid
        ELSE stg_.post_artist_links.artist_mbid
    END,
    method = CASE
        WHEN excluded.join_key_type = 'mbid'
            THEN excluded.method
        ELSE stg_.post_artist_links.method
    END,
    score = CASE
        WHEN excluded.join_key_type = 'mbid'
            THEN excluded.score
        ELSE stg_.post_artist_links.score
    END,
    join_key_type = CASE
        WHEN excluded.join_key_type = 'mbid'
            THEN excluded.join_key_type
        ELSE stg_.post_artist_links.join_key_type
    END,
    resolved_at = CASE
        WHEN excluded.join_key_type = 'mbid'
            THEN excluded.resolved_at
        ELSE stg_.post_artist_links.resolved_at
    END;

