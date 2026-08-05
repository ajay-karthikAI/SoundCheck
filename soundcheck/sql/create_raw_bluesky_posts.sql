SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.bluesky_posts (
    uri VARCHAR NOT NULL,
    did VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    text VARCHAR NOT NULL,
    langs VARCHAR[] NOT NULL,
    link_urls VARCHAR[] NOT NULL,
    hashtags VARCHAR[] NOT NULL,
    matched_rules VARCHAR[] NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL
);
