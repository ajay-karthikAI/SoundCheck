SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.conversation_evidence_v2 (
    taxonomy_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    post_uri VARCHAR NOT NULL,
    did VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    text VARCHAR NOT NULL,
    likes BIGINT NOT NULL,
    reposts BIGINT NOT NULL,
    replies BIGINT NOT NULL,
    artist_name_raw VARCHAR NOT NULL,
    resolution_method VARCHAR NOT NULL,
    resolution_score DOUBLE NOT NULL,
    join_key_type VARCHAR NOT NULL,
    membership_weight DOUBLE NOT NULL,
    membership_method VARCHAR NOT NULL,
    membership_confidence DOUBLE NOT NULL,
    PRIMARY KEY (taxonomy_version, week_start, genre_id, post_uri)
);

CREATE TABLE IF NOT EXISTS mart_.listening_evidence_v2 (
    taxonomy_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    artist_key VARCHAR NOT NULL,
    artist_name VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    playcount BIGINT NOT NULL,
    listeners BIGINT NOT NULL,
    previous_playcount BIGINT NOT NULL,
    previous_listeners BIGINT NOT NULL,
    playcount_delta BIGINT NOT NULL,
    listeners_delta BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    previous_fetched_at TIMESTAMPTZ NOT NULL,
    interval_days DOUBLE NOT NULL,
    listening_window_status VARCHAR NOT NULL,
    membership_weight DOUBLE NOT NULL,
    membership_method VARCHAR NOT NULL,
    membership_confidence DOUBLE NOT NULL,
    PRIMARY KEY (taxonomy_version, week_start, genre_id, artist_key),
    CHECK (listening_window_status = 'valid_weekly')
);

ALTER TABLE mart_.listening_evidence_v2
ADD COLUMN IF NOT EXISTS interval_days DOUBLE;

ALTER TABLE mart_.listening_evidence_v2
ADD COLUMN IF NOT EXISTS listening_window_status VARCHAR;

CREATE TABLE IF NOT EXISTS mart_.supply_evidence_v2 (
    taxonomy_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    release_group_mbid VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    artist_credits STRUCT(
        credit_name VARCHAR,
        artist_name VARCHAR,
        mbid VARCHAR,
        join_phrase VARCHAR
    )[] NOT NULL,
    first_release_date DATE NOT NULL,
    types VARCHAR[] NOT NULL,
    genres VARCHAR[] NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    membership_weight DOUBLE NOT NULL,
    PRIMARY KEY (
        taxonomy_version,
        week_start,
        genre_id,
        release_group_mbid
    )
);
