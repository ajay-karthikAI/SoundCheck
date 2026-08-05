WITH settings AS (
    SELECT CAST(? AS TIMESTAMPTZ) AS as_of
)
SELECT DISTINCT post.uri
FROM raw_.bluesky_posts AS post
CROSS JOIN settings
WHERE
    (
        post.created_at
            BETWEEN settings.as_of - INTERVAL 36 HOUR
            AND settings.as_of - INTERVAL 18 HOUR
        AND NOT EXISTS (
            SELECT 1
            FROM raw_.bluesky_engagement AS engagement
            WHERE
                engagement.uri = post.uri
                AND engagement.fetched_at
                    BETWEEN post.created_at + INTERVAL 18 HOUR
                    AND post.created_at + INTERVAL 36 HOUR
        )
    )
    OR (
        post.created_at
            BETWEEN settings.as_of - INTERVAL 84 HOUR
            AND settings.as_of - INTERVAL 60 HOUR
        AND NOT EXISTS (
            SELECT 1
            FROM raw_.bluesky_engagement AS engagement
            WHERE
                engagement.uri = post.uri
                AND engagement.fetched_at
                    BETWEEN post.created_at + INTERVAL 60 HOUR
                    AND post.created_at + INTERVAL 84 HOUR
        )
    )
ORDER BY post.uri;
