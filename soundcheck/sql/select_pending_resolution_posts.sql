WITH latest_posts AS (
    SELECT
        uri,
        text,
        link_urls,
        row_number() OVER (
            PARTITION BY uri
            ORDER BY ingested_at DESC
        ) AS recency_rank
    FROM raw_.bluesky_posts
),
upstream_watermark AS (
    SELECT greatest(
        coalesce(
            (
                SELECT max(fetched_at)
                FROM raw_.lastfm_artist_snapshots
            ),
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        ),
        coalesce(
            (
                SELECT max(fetched_at)
                FROM raw_.mb_release_groups
            ),
            TIMESTAMPTZ '1970-01-01 00:00:00+00'
        )
    ) AS updated_at
)
SELECT
    post.uri,
    post.text,
    post.link_urls
FROM latest_posts AS post
LEFT JOIN stg_.post_artist_resolution_attempts AS attempt
    ON attempt.post_uri = post.uri
LEFT JOIN stg_.post_artist_links AS existing_link
    ON
        existing_link.post_uri = post.uri
        AND existing_link.join_key_type = 'name'
CROSS JOIN upstream_watermark
WHERE
    post.recency_rank = 1
    AND (
        attempt.post_uri IS NULL
        OR (
            upstream_watermark.updated_at > attempt.attempted_at
            AND (
                attempt.outcome <> 'resolved'
                OR existing_link.post_uri IS NOT NULL
            )
        )
    )
GROUP BY
    post.uri,
    post.text,
    post.link_urls
ORDER BY post.uri;
