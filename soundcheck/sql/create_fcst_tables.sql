SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS fcst_;

CREATE TABLE IF NOT EXISTS fcst_.backtest_ledger (
    canonical_genre VARCHAR NOT NULL,
    target_axis VARCHAR NOT NULL,
    horizon INTEGER NOT NULL,
    model_name VARCHAR NOT NULL,
    origin_week DATE NOT NULL,
    target_week DATE NOT NULL,
    training_start_week DATE NOT NULL,
    training_end_week DATE NOT NULL,
    training_weeks INTEGER NOT NULL,
    actual DOUBLE NOT NULL,
    prediction DOUBLE NOT NULL,
    interval_low DOUBLE NOT NULL,
    interval_high DOUBLE NOT NULL,
    absolute_error DOUBLE NOT NULL,
    covered_80 BOOLEAN NOT NULL,
    PRIMARY KEY (
        canonical_genre,
        target_axis,
        horizon,
        model_name,
        origin_week
    )
);

CREATE TABLE IF NOT EXISTS fcst_.model_scores (
    canonical_genre VARCHAR NOT NULL,
    target_axis VARCHAR NOT NULL,
    horizon INTEGER NOT NULL,
    model_name VARCHAR NOT NULL,
    backtest_start_week DATE NOT NULL,
    backtest_end_week DATE NOT NULL,
    origin_count INTEGER NOT NULL,
    mae DOUBLE NOT NULL,
    naive_mae DOUBLE NOT NULL,
    mase DOUBLE,
    interval_coverage_80 DOUBLE NOT NULL,
    mean_interval_width DOUBLE NOT NULL,
    score_status VARCHAR NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        canonical_genre,
        target_axis,
        horizon,
        model_name
    )
);

CREATE TABLE IF NOT EXISTS fcst_.predictions (
    origin_week DATE NOT NULL,
    target_week DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    target_axis VARCHAR NOT NULL,
    horizon INTEGER NOT NULL,
    model_name VARCHAR NOT NULL,
    is_naive_baseline BOOLEAN NOT NULL,
    skill_status VARCHAR NOT NULL,
    prediction DOUBLE NOT NULL,
    interval_low DOUBLE NOT NULL,
    interval_high DOUBLE NOT NULL,
    backtest_mase DOUBLE,
    backtest_coverage_80 DOUBLE NOT NULL,
    backtest_origin_count INTEGER NOT NULL,
    training_start_week DATE NOT NULL,
    training_end_week DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        origin_week,
        canonical_genre,
        target_axis,
        horizon,
        model_name
    )
);

CREATE TABLE IF NOT EXISTS fcst_.next_up (
    origin_week DATE NOT NULL,
    target_week DATE NOT NULL,
    canonical_genre VARCHAR NOT NULL,
    rank INTEGER NOT NULL,
    predicted_opportunity DOUBLE NOT NULL,
    predicted_opportunity_interval_low DOUBLE NOT NULL,
    predicted_opportunity_interval_high DOUBLE NOT NULL,
    predicted_gain DOUBLE NOT NULL,
    gain_interval_low DOUBLE NOT NULL,
    gain_interval_high DOUBLE NOT NULL,
    conversation_model VARCHAR NOT NULL,
    listening_model VARCHAR NOT NULL,
    conversation_mase DOUBLE,
    listening_mase DOUBLE,
    skill_status VARCHAR NOT NULL,
    breakout_evidence_week DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (origin_week, canonical_genre)
);

-- Phase 5 initially made MASE non-null. It is mathematically undefined when
-- the naive baseline has zero error, so keep these migrations idempotent for
-- databases initialized by that early schema.
ALTER TABLE fcst_.predictions
    ALTER COLUMN backtest_mase DROP NOT NULL;
ALTER TABLE fcst_.next_up
    ALTER COLUMN conversation_mase DROP NOT NULL;
ALTER TABLE fcst_.next_up
    ALTER COLUMN listening_mase DROP NOT NULL;
ALTER TABLE fcst_.next_up ADD COLUMN IF NOT EXISTS
    predicted_opportunity_interval_low DOUBLE;
ALTER TABLE fcst_.next_up ADD COLUMN IF NOT EXISTS
    predicted_opportunity_interval_high DOUBLE;
