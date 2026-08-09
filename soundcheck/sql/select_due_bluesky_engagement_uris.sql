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
)
SELECT
    polls.uri,
    CASE
        WHEN
            NOT coalesce(polls.has_72h, false)
            AND polls.created_at BETWEEN
                settings.as_of - INTERVAL 84 HOUR
                AND settings.as_of - INTERVAL 60 HOUR
            THEN 72
        ELSE 24
    END AS poll_target_hours,
    'scheduled' AS poll_status
FROM polls
CROSS JOIN settings
WHERE
    (
        NOT coalesce(polls.has_24h, false)
        AND polls.created_at BETWEEN
            settings.as_of - INTERVAL 36 HOUR
            AND settings.as_of - INTERVAL 18 HOUR
    )
    OR (
        NOT coalesce(polls.has_72h, false)
        AND polls.created_at BETWEEN
            settings.as_of - INTERVAL 84 HOUR
            AND settings.as_of - INTERVAL 60 HOUR
    )
ORDER BY polls.uri;
