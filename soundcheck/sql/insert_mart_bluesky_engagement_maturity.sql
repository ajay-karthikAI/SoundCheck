INSERT INTO mart_.bluesky_engagement_maturity (
    post_uri,
    created_at,
    as_of,
    has_24h_snapshot,
    has_72h_snapshot,
    latest_engagement_fetched_at,
    like_count,
    repost_count,
    reply_count,
    engagement_maturity_status
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
