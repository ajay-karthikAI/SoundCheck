SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS stg_;

CREATE TABLE IF NOT EXISTS stg_.post_artist_links (
    post_uri VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    artist_name_raw VARCHAR NOT NULL,
    method VARCHAR NOT NULL,
    score DOUBLE NOT NULL,
    join_key_type VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (post_uri, artist_name_raw)
);

CREATE TABLE IF NOT EXISTS stg_.post_artist_ambiguities (
    post_uri VARCHAR NOT NULL,
    artist_name_raw VARCHAR NOT NULL,
    top_artist_mbid VARCHAR NOT NULL,
    top_artist_name VARCHAR NOT NULL,
    top_score DOUBLE NOT NULL,
    second_artist_mbid VARCHAR NOT NULL,
    second_artist_name VARCHAR NOT NULL,
    second_score DOUBLE NOT NULL,
    reason VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (post_uri, artist_name_raw)
);

CREATE TABLE IF NOT EXISTS stg_.post_artist_resolution_attempts (
    post_uri VARCHAR PRIMARY KEY,
    outcome VARCHAR NOT NULL,
    candidate_count INTEGER NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL
);

