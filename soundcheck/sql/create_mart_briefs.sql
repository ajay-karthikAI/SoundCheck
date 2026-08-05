SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.briefs (
    brief_id VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    headline VARCHAR NOT NULL,
    opportunity DOUBLE NOT NULL,
    opportunity_ci_low DOUBLE NOT NULL,
    opportunity_ci_high DOUBLE NOT NULL,
    rationale VARCHAR NOT NULL,
    recommended_actions VARCHAR[] NOT NULL,
    evidence_uris VARCHAR[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (week_start, canonical_genre),
    UNIQUE (brief_id)
);

CREATE TABLE IF NOT EXISTS mart_.briefs_v2 (
    taxonomy_version VARCHAR NOT NULL,
    brief_id VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    macro_family_id VARCHAR NOT NULL,
    parent_genre_id VARCHAR,
    coverage_status VARCHAR NOT NULL,
    context VARCHAR NOT NULL,
    headline VARCHAR NOT NULL,
    opportunity DOUBLE NOT NULL,
    opportunity_ci_low DOUBLE NOT NULL,
    opportunity_ci_high DOUBLE NOT NULL,
    forecast_direction DOUBLE NOT NULL,
    forecast_interval_low DOUBLE NOT NULL,
    forecast_interval_high DOUBLE NOT NULL,
    forecast_model VARCHAR NOT NULL,
    backtest_mase DOUBLE,
    backtest_coverage_80 DOUBLE NOT NULL,
    rationale VARCHAR NOT NULL,
    recommended_actions VARCHAR[] NOT NULL,
    evidence_uris VARCHAR[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (taxonomy_version, week_start, context, genre_id),
    UNIQUE (taxonomy_version, brief_id)
);
