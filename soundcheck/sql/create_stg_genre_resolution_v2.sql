SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS stg_;

CREATE TABLE IF NOT EXISTS stg_.tag_genre_map_v2 (
    source_system VARCHAR NOT NULL,
    source_tag VARCHAR NOT NULL,
    normalized_source_tag VARCHAR NOT NULL,
    canonical_genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    parent_genre_id VARCHAR,
    membership_weight DOUBLE NOT NULL,
    method VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    language VARCHAR NOT NULL,
    model_name VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        taxonomy_version,
        source_system,
        normalized_source_tag,
        canonical_genre_id
    ),
    CHECK (membership_weight BETWEEN 0 AND 1),
    CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS stg_.canonical_genre_embeddings_v2 (
    canonical_genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    parent_genre_id VARCHAR,
    embedding FLOAT[] NOT NULL,
    model_name VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, canonical_genre_id)
);

CREATE TABLE IF NOT EXISTS stg_.artist_genre_memberships_v2 (
    artist_key_type VARCHAR NOT NULL,
    artist_key VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    artist_name VARCHAR NOT NULL,
    canonical_genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    parent_genre_id VARCHAR,
    membership_weight DOUBLE NOT NULL,
    method VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    source_systems VARCHAR[] NOT NULL,
    source_tags VARCHAR[] NOT NULL,
    input_fingerprint VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, artist_key, canonical_genre_id),
    CHECK (artist_key_type IN ('mbid', 'name')),
    CHECK (membership_weight BETWEEN 0 AND 1),
    CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS stg_.artist_genre_resolution_state_v2 (
    artist_key VARCHAR NOT NULL,
    input_fingerprint VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, artist_key)
);

CREATE TABLE IF NOT EXISTS stg_.genre_family_activation_v2 (
    macro_family_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    production_eligible BOOLEAN NOT NULL,
    labeled_examples INTEGER NOT NULL,
    precision DOUBLE,
    recall DOUBLE,
    mbid_precision DOUBLE,
    reasons VARCHAR[] NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, macro_family_id),
    CHECK (status IN ('active', 'candidate')),
    CHECK (production_eligible = (status = 'active'))
);
