SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.bluesky_engagement (
    uri VARCHAR NOT NULL,
    like_count BIGINT NOT NULL,
    repost_count BIGINT NOT NULL,
    reply_count BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    poll_target_hours INTEGER,
    poll_status VARCHAR
);

ALTER TABLE raw_.bluesky_engagement
    ADD COLUMN IF NOT EXISTS poll_target_hours INTEGER;

ALTER TABLE raw_.bluesky_engagement
    ADD COLUMN IF NOT EXISTS poll_status VARCHAR;
