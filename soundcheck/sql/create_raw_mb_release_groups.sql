SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.mb_release_groups (
    release_group_mbid VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    artist_credits STRUCT(
        credit_name VARCHAR,
        artist_name VARCHAR,
        mbid VARCHAR,
        join_phrase VARCHAR
    )[] NOT NULL,
    artist_mbids VARCHAR[] NOT NULL,
    first_release_date VARCHAR NOT NULL,
    types VARCHAR[] NOT NULL,
    genres VARCHAR[] NOT NULL,
    tags STRUCT(
        name VARCHAR,
        count BIGINT
    )[] NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

