SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.bluesky_engagement_maturity (
    post_uri VARCHAR PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    has_24h_snapshot BOOLEAN NOT NULL,
    has_72h_snapshot BOOLEAN NOT NULL,
    latest_engagement_fetched_at TIMESTAMPTZ,
    like_count BIGINT,
    repost_count BIGINT,
    reply_count BIGINT,
    engagement_maturity_status VARCHAR NOT NULL,
    CHECK (
        engagement_maturity_status IN (
            'awaiting_24h',
            'overdue_24h',
            'awaiting_72h',
            'overdue_72h',
            'complete'
        )
    )
);

CREATE TABLE IF NOT EXISTS mart_.genre_week_axis_maturity (
    artifact_family VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    conversation_maturity VARCHAR NOT NULL,
    listening_maturity VARCHAR NOT NULL,
    supply_maturity VARCHAR NOT NULL,
    decision_ready BOOLEAN NOT NULL,
    conversation_post_count BIGINT NOT NULL,
    mature_conversation_post_count BIGINT NOT NULL,
    valid_listening_artist_count BIGINT NOT NULL,
    supply_release_group_count BIGINT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (artifact_family, taxonomy_version, week_start, genre_id),
    CHECK (artifact_family IN ('v1', 'v2')),
    CHECK (conversation_maturity IN ('conversation_pending', 'complete')),
    CHECK (listening_maturity IN ('listening_pending', 'complete')),
    CHECK (supply_maturity IN ('supply_pending', 'complete'))
);
