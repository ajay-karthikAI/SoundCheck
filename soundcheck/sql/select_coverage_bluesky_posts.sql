SELECT
    uri,
    created_at,
    ingested_at
FROM raw_.bluesky_posts
QUALIFY row_number() OVER (
    PARTITION BY uri
    ORDER BY ingested_at DESC
) = 1
ORDER BY created_at, uri;
