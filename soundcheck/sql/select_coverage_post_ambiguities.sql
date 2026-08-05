SELECT
    post_uri,
    top_artist_mbid,
    top_artist_name,
    resolved_at
FROM stg_.post_artist_ambiguities
ORDER BY post_uri, artist_name_raw;
