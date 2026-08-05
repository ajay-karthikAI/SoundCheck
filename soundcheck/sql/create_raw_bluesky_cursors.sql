SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.bluesky_cursor_checkpoints (
    time_us BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
