SET TimeZone = 'UTC';

WITH latest_posts AS (
    SELECT uri, did, created_at, text
    FROM raw_.bluesky_posts
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY ingested_at DESC
    ) = 1
),
preferred_links AS (
    SELECT
        post_uri,
        artist_mbid,
        artist_name_raw,
        method,
        score,
        join_key_type
    FROM stg_.post_artist_links
    QUALIFY row_number() OVER (
        PARTITION BY post_uri
        ORDER BY
            (join_key_type = 'mbid') DESC,
            score DESC,
            resolved_at DESC
    ) = 1
),
latest_engagement AS (
    SELECT uri, like_count, repost_count, reply_count
    FROM raw_.bluesky_engagement
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY fetched_at DESC
    ) = 1
),
post_memberships AS (
    SELECT
        post.uri,
        CAST(date_trunc('week', post.created_at) AS DATE) AS week_start,
        membership.canonical_genre_id,
        membership.macro_family_id,
        membership.membership_weight,
        membership.method AS membership_method,
        membership.confidence AS membership_confidence,
        link.artist_name_raw,
        link.method AS resolution_method,
        link.score AS resolution_score,
        link.join_key_type
    FROM latest_posts AS post
    JOIN preferred_links AS link
        ON link.post_uri = post.uri
    JOIN stg_.artist_genre_memberships_v2 AS membership
        ON membership.taxonomy_version = ?
        AND (
            (
                link.artist_mbid IS NOT NULL
                AND lower(membership.artist_mbid) = lower(link.artist_mbid)
            )
            OR (
                link.artist_mbid IS NULL
                AND lower(trim(membership.artist_name))
                    = lower(trim(link.artist_name_raw))
            )
        )
    QUALIFY row_number() OVER (
        PARTITION BY post.uri, membership.canonical_genre_id
        ORDER BY
            membership.confidence DESC,
            membership.membership_weight DESC,
            membership.resolved_at DESC
    ) = 1
)
SELECT
    post.week_start,
    post.canonical_genre_id,
    post.macro_family_id,
    post.uri,
    post.membership_weight,
    coalesce(engagement.like_count, 0),
    coalesce(engagement.repost_count, 0),
    coalesce(engagement.reply_count, 0),
    source.did,
    source.created_at,
    source.text,
    post.artist_name_raw,
    post.resolution_method,
    post.resolution_score,
    post.join_key_type,
    post.membership_method,
    post.membership_confidence
FROM post_memberships AS post
JOIN latest_posts AS source
    ON source.uri = post.uri
LEFT JOIN latest_engagement AS engagement
    ON engagement.uri = post.uri
ORDER BY post.week_start, post.canonical_genre_id, post.uri;
