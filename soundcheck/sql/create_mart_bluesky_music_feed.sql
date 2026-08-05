CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.bluesky_music_feed (
    week_start DATE NOT NULL,
    uri VARCHAR PRIMARY KEY,
    did VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    text VARCHAR NOT NULL,
    link_urls VARCHAR[] NOT NULL,
    hashtags VARCHAR[] NOT NULL,
    matched_rules VARCHAR[] NOT NULL,
    like_count BIGINT NOT NULL,
    repost_count BIGINT NOT NULL,
    reply_count BIGINT NOT NULL
);
