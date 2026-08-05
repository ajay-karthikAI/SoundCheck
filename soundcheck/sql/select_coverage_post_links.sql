SELECT
    post_uri,
    artist_mbid,
    artist_name_raw,
    method,
    score,
    join_key_type,
    resolved_at
FROM stg_.post_artist_links
ORDER BY post_uri, artist_name_raw;
