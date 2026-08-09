WITH settings AS (
    SELECT CAST(? AS TIMESTAMPTZ) AS as_of
),
latest_posts AS (
    SELECT uri, created_at
    FROM raw_.bluesky_posts
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY ingested_at DESC
    ) = 1
),
poll_flags AS (
    SELECT
        post.uri,
        post.created_at,
        bool_or(
            engagement.poll_target_hours = 24
            OR (
                engagement.poll_target_hours IS NULL
                AND engagement.fetched_at BETWEEN
                    post.created_at + INTERVAL 18 HOUR
                    AND post.created_at + INTERVAL 36 HOUR
            )
        ) AS has_24h_snapshot,
        bool_or(
            engagement.poll_target_hours = 72
            OR (
                engagement.poll_target_hours IS NULL
                AND engagement.fetched_at >= post.created_at + INTERVAL 60 HOUR
            )
        ) AS has_72h_snapshot
    FROM latest_posts AS post
    LEFT JOIN raw_.bluesky_engagement AS engagement
        ON engagement.uri = post.uri
    GROUP BY post.uri, post.created_at
),
final_engagement AS (
    SELECT
        post.uri,
        engagement.like_count,
        engagement.repost_count,
        engagement.reply_count,
        engagement.fetched_at
    FROM latest_posts AS post
    JOIN raw_.bluesky_engagement AS engagement
        ON engagement.uri = post.uri
    WHERE
        engagement.poll_target_hours = 72
        OR (
            engagement.poll_target_hours IS NULL
            AND engagement.fetched_at >= post.created_at + INTERVAL 60 HOUR
        )
    QUALIFY row_number() OVER (
        PARTITION BY post.uri
        ORDER BY engagement.fetched_at DESC
    ) = 1
)
SELECT
    post.uri,
    post.created_at,
    settings.as_of,
    coalesce(flags.has_24h_snapshot, false),
    coalesce(flags.has_72h_snapshot, false),
    final.fetched_at,
    final.like_count,
    final.repost_count,
    final.reply_count,
    CASE
        WHEN coalesce(flags.has_72h_snapshot, false) THEN 'complete'
        WHEN settings.as_of < post.created_at + INTERVAL 18 HOUR THEN 'awaiting_24h'
        WHEN
            NOT coalesce(flags.has_24h_snapshot, false)
            AND settings.as_of >= post.created_at + INTERVAL 36 HOUR
            AND settings.as_of < post.created_at + INTERVAL 60 HOUR
            THEN 'overdue_24h'
        WHEN settings.as_of < post.created_at + INTERVAL 60 HOUR THEN 'awaiting_72h'
        ELSE 'overdue_72h'
    END
FROM latest_posts AS post
CROSS JOIN settings
LEFT JOIN poll_flags AS flags ON flags.uri = post.uri
LEFT JOIN final_engagement AS final ON final.uri = post.uri
ORDER BY post.uri;
