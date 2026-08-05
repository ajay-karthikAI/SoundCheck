SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.bluesky_engagement (
    uri VARCHAR NOT NULL,
    like_count BIGINT NOT NULL,
    repost_count BIGINT NOT NULL,
    reply_count BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);
