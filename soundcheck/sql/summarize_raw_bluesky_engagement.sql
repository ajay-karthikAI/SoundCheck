SELECT
    count(*),
    count(DISTINCT fetched_at)
FROM raw_.bluesky_engagement;

