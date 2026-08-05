SELECT
    post_uri,
    artist_mbid,
    artist_name_raw,
    method,
    join_key_type
FROM stg_.post_artist_links
QUALIFY row_number() OVER (
    PARTITION BY post_uri
    ORDER BY
        (join_key_type = 'mbid') DESC,
        score DESC
) = 1
ORDER BY post_uri;

