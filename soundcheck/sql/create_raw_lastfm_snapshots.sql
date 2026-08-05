SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS raw_;

CREATE TABLE IF NOT EXISTS raw_.lastfm_tag_snapshots (
    tag VARCHAR NOT NULL,
    reach BIGINT NOT NULL,
    total BIGINT NOT NULL,
    top_artists STRUCT(
        name VARCHAR,
        mbid VARCHAR,
        rank INTEGER
    )[] NOT NULL,
    top_albums STRUCT(
        title VARCHAR,
        mbid VARCHAR,
        artist_name VARCHAR,
        artist_mbid VARCHAR,
        rank INTEGER
    )[] NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_.lastfm_artist_snapshots (
    artist_name VARCHAR NOT NULL,
    mbid VARCHAR,
    listeners BIGINT NOT NULL,
    playcount BIGINT NOT NULL,
    tags VARCHAR[] NOT NULL,
    source_genres VARCHAR[] NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

