SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.genre_coverage_v2 (
    taxonomy_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    genre_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    slug VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    macro_family_name VARCHAR NOT NULL,
    taxonomy_status VARCHAR NOT NULL,
    lastfm_tag_available BOOLEAN,
    unique_lastfm_artists BIGINT,
    artists_with_consecutive_valid_snapshots BIGINT,
    lastfm_history_weeks INTEGER,
    musicbrainz_release_group_count BIGINT,
    resolved_bluesky_post_count BIGINT,
    resolution_attempt_count BIGINT,
    resolution_rate DOUBLE,
    cross_source_overlap_artist_count BIGINT,
    cross_source_overlap DOUBLE,
    latest_source_timestamp TIMESTAMPTZ,
    listening_missing BOOLEAN NOT NULL,
    conversation_missing BOOLEAN NOT NULL,
    supply_missing BOOLEAN NOT NULL,
    stale BOOLEAN NOT NULL,
    eligibility_state VARCHAR NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, week_start, genre_id),
    CHECK (taxonomy_status IN ('enabled', 'candidate', 'rejected')),
    CHECK (
        eligibility_state IN (
            'ready',
            'collecting_history',
            'insufficient_listening',
            'insufficient_conversation',
            'insufficient_supply',
            'insufficient_resolution',
            'unsupported'
        )
    )
);
