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
polls AS (
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
        ) AS has_24h,
        bool_or(
            engagement.poll_target_hours = 72
            OR (
                engagement.poll_target_hours IS NULL
                AND engagement.fetched_at >= post.created_at + INTERVAL 60 HOUR
            )
        ) AS has_72h
    FROM latest_posts AS post
    LEFT JOIN raw_.bluesky_engagement AS engagement
        ON engagement.uri = post.uri
    GROUP BY post.uri, post.created_at
),
eligible AS (
    SELECT
        polls.uri,
        CASE
            WHEN settings.as_of >= polls.created_at + INTERVAL 60 HOUR THEN 72
            ELSE 24
        END AS poll_target_hours,
        'overdue_recovery' AS poll_status,
        polls.created_at
    FROM polls
    CROSS JOIN settings
    WHERE
        (
            settings.as_of >= polls.created_at + INTERVAL 84 HOUR
            AND NOT coalesce(polls.has_72h, false)
        )
        OR (
            settings.as_of >= polls.created_at + INTERVAL 36 HOUR
            AND settings.as_of < polls.created_at + INTERVAL 60 HOUR
            AND NOT coalesce(polls.has_24h, false)
        )
)
SELECT uri, poll_target_hours, poll_status
FROM eligible
ORDER BY created_at, uri
LIMIT ?;
