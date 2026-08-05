SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.pipeline_runs (
    run_id VARCHAR PRIMARY KEY,
    run_kind VARCHAR NOT NULL,
    trigger_name VARCHAR NOT NULL,
    git_sha VARCHAR,
    status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    wall_time_seconds DOUBLE,
    bluesky_posts_ingested BIGINT NOT NULL DEFAULT 0,
    bluesky_engagement_snapshots_ingested BIGINT NOT NULL DEFAULT 0,
    lastfm_tag_snapshots_ingested BIGINT NOT NULL DEFAULT 0,
    lastfm_artist_snapshots_ingested BIGINT NOT NULL DEFAULT 0,
    musicbrainz_release_groups_ingested BIGINT NOT NULL DEFAULT 0,
    resolution_posts_attempted BIGINT NOT NULL DEFAULT 0,
    resolution_links_resolved BIGINT NOT NULL DEFAULT 0,
    resolution_rate DOUBLE,
    metric_rows BIGINT NOT NULL DEFAULT 0,
    forecast_rows BIGINT NOT NULL DEFAULT 0,
    brief_rows BIGINT NOT NULL DEFAULT 0,
    error_message VARCHAR
);

ALTER TABLE mart_.pipeline_runs ADD COLUMN IF NOT EXISTS
    bluesky_engagement_snapshots_ingested BIGINT DEFAULT 0;
