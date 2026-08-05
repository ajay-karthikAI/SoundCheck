SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.scene_map (
    as_of_week DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    x DOUBLE NOT NULL,
    y DOUBLE NOT NULL,
    opportunity DOUBLE,
    opportunity_ci_low DOUBLE,
    opportunity_ci_high DOUBLE,
    discovery_gap DOUBLE,
    discovery_gap_ci_low DOUBLE,
    discovery_gap_ci_high DOUBLE,
    evidence_volume INTEGER NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (as_of_week, canonical_genre)
);

CREATE TABLE IF NOT EXISTS mart_.scene_map_v2 (
    taxonomy_version VARCHAR NOT NULL,
    as_of_week DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    parent_genre_id VARCHAR,
    coverage_status VARCHAR NOT NULL,
    context VARCHAR NOT NULL,
    x DOUBLE NOT NULL,
    y DOUBLE NOT NULL,
    opportunity DOUBLE,
    opportunity_ci_low DOUBLE,
    opportunity_ci_high DOUBLE,
    discovery_gap DOUBLE,
    discovery_gap_ci_low DOUBLE,
    discovery_gap_ci_high DOUBLE,
    evidence_volume INTEGER NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        taxonomy_version,
        as_of_week,
        context,
        genre_id
    )
);
