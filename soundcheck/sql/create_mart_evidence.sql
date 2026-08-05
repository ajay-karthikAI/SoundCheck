SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.conversation_evidence (
    week_start DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    post_uri VARCHAR NOT NULL,
    did VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    text VARCHAR NOT NULL,
    like_count BIGINT NOT NULL,
    repost_count BIGINT NOT NULL,
    reply_count BIGINT NOT NULL,
    weighted_score DOUBLE NOT NULL,
    artist_name_raw VARCHAR NOT NULL,
    resolution_method VARCHAR NOT NULL,
    resolution_score DOUBLE NOT NULL,
    join_key_type VARCHAR NOT NULL,
    PRIMARY KEY (week_start, canonical_genre, post_uri)
);

CREATE TABLE IF NOT EXISTS mart_.listening_evidence (
    week_start DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    artist_key VARCHAR NOT NULL,
    artist_name VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    playcount_delta BIGINT NOT NULL,
    listeners_delta BIGINT NOT NULL,
    weighted_delta BIGINT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (week_start, canonical_genre, artist_key)
);

CREATE TABLE IF NOT EXISTS mart_.supply_evidence (
    week_start DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
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
    PRIMARY KEY (week_start, canonical_genre, release_group_mbid)
);
