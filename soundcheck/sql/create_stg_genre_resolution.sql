SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS stg_;

CREATE TABLE IF NOT EXISTS stg_.tag_genre_map (
    source_system VARCHAR NOT NULL,
    raw_tag VARCHAR NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    similarity DOUBLE NOT NULL,
    method VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source_system, raw_tag)
);

CREATE TABLE IF NOT EXISTS stg_.canonical_genre_embeddings (
    canonical_genre VARCHAR PRIMARY KEY,
    embedding FLOAT[] NOT NULL,
    model_name VARCHAR NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL
);

