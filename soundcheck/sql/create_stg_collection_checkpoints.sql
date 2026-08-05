SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS stg_;

CREATE TABLE IF NOT EXISTS stg_.collection_checkpoints (
    source VARCHAR NOT NULL,
    run_key VARCHAR NOT NULL,
    phase VARCHAR NOT NULL,
    unit_key VARCHAR NOT NULL,
    shard_index INTEGER,
    payload_json VARCHAR NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (source, run_key, phase, unit_key),
    CHECK (source IN ('lastfm', 'musicbrainz'))
);
