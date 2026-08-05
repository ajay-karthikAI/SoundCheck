WITH latest_posts AS (
    SELECT
        uri,
        text,
        link_urls,
        ingested_at,
        row_number() OVER (
            PARTITION BY uri
            ORDER BY ingested_at DESC
        ) AS recency_rank
    FROM raw_.bluesky_posts
),
preferred_links AS (
    SELECT
        post_uri,
        artist_mbid,
        artist_name_raw,
        method,
        join_key_type,
        row_number() OVER (
            PARTITION BY post_uri
            ORDER BY
                (join_key_type = 'mbid') DESC,
                score DESC
        ) AS preference_rank
    FROM stg_.post_artist_links
)
SELECT
    post.uri,
    post.text,
    post.link_urls,
    link.artist_mbid,
    link.artist_name_raw,
    link.method,
    link.join_key_type
FROM latest_posts AS post
LEFT JOIN preferred_links AS link
    ON
        link.post_uri = post.uri
        AND link.preference_rank = 1
WHERE post.recency_rank = 1
ORDER BY post.ingested_at DESC
LIMIT ?;

