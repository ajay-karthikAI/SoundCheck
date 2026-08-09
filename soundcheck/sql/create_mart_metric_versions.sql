SET TimeZone = 'UTC';

CREATE SCHEMA IF NOT EXISTS mart_;

CREATE TABLE IF NOT EXISTS mart_.metric_artifact_versions (
    artifact_family VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    derivation_version VARCHAR NOT NULL,
    validation_status VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL,
    validated_at TIMESTAMPTZ NOT NULL,
    withdrawal_count BIGINT NOT NULL,
    PRIMARY KEY (artifact_family, taxonomy_version, derivation_version),
    CHECK (artifact_family IN ('v1', 'v2')),
    CHECK (validation_status = 'validated')
);

CREATE TABLE IF NOT EXISTS mart_.genre_weekly_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.genre_weekly AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.ecosystem_weekly_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.ecosystem_weekly AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.genre_weekly_v2_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.genre_weekly_v2 AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.metric_estimates_v2_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.metric_estimates_v2 AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.macro_family_weekly_v2_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.macro_family_weekly_v2 AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.ecosystem_weekly_v2_versioned AS
SELECT CAST(NULL AS VARCHAR) AS derivation_version, source.*
FROM mart_.ecosystem_weekly_v2 AS source
WHERE false;

CREATE TABLE IF NOT EXISTS mart_.lastfm_listening_windows (
    artifact_family VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    derivation_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    genre_id VARCHAR NOT NULL,
    macro_family_id VARCHAR,
    artist_key VARCHAR NOT NULL,
    artist_name VARCHAR NOT NULL,
    artist_mbid VARCHAR,
    membership_weight DOUBLE NOT NULL,
    playcount BIGINT NOT NULL,
    listeners BIGINT NOT NULL,
    previous_playcount BIGINT,
    previous_listeners BIGINT,
    previous_fetched_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    interval_days DOUBLE,
    observations_append_only BOOLEAN NOT NULL,
    listening_window_status VARCHAR NOT NULL,
    membership_method VARCHAR,
    membership_confidence DOUBLE,
    PRIMARY KEY (
        artifact_family,
        taxonomy_version,
        derivation_version,
        week_start,
        genre_id,
        artist_key
    ),
    CHECK (
        listening_window_status IN (
            'valid_weekly',
            'first_observation',
            'incomplete_pair',
            'not_append_only',
            'invalid_order',
            'same_week_duplicate',
            'nonconsecutive_weeks',
            'counter_decrease'
        )
    ),
    CHECK (
        listening_window_status <> 'valid_weekly'
        OR (
            previous_fetched_at IS NOT NULL
            AND interval_days > 0
            AND observations_append_only
        )
    )
);

CREATE TABLE IF NOT EXISTS mart_.metric_row_withdrawals (
    artifact_family VARCHAR NOT NULL,
    taxonomy_version VARCHAR NOT NULL,
    derivation_version VARCHAR NOT NULL,
    week_start DATE NOT NULL,
    scope_id VARCHAR NOT NULL,
    previous_opportunity DOUBLE NOT NULL,
    previous_discovery_gap DOUBLE,
    withdrawal_reason VARCHAR NOT NULL,
    PRIMARY KEY (
        artifact_family,
        taxonomy_version,
        derivation_version,
        week_start,
        scope_id
    )
);

CREATE OR REPLACE VIEW mart_.genre_weekly_production AS
WITH active AS (
    SELECT derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v1'
        AND taxonomy_version = 'v1'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.genre_weekly_versioned AS versioned
INNER JOIN active USING (derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.genre_weekly AS legacy
WHERE NOT EXISTS (SELECT 1 FROM active);

CREATE OR REPLACE VIEW mart_.ecosystem_weekly_production AS
WITH active AS (
    SELECT derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v1'
        AND taxonomy_version = 'v1'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.ecosystem_weekly_versioned AS versioned
INNER JOIN active USING (derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.ecosystem_weekly AS legacy
WHERE NOT EXISTS (SELECT 1 FROM active);

CREATE OR REPLACE VIEW mart_.genre_weekly_v2_production AS
WITH active AS (
    SELECT taxonomy_version, derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v2'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.genre_weekly_v2_versioned AS versioned
INNER JOIN active USING (taxonomy_version, derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.genre_weekly_v2 AS legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM active
    WHERE active.taxonomy_version = legacy.taxonomy_version
);

CREATE OR REPLACE VIEW mart_.metric_estimates_v2_production AS
WITH active AS (
    SELECT taxonomy_version, derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v2'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.metric_estimates_v2_versioned AS versioned
INNER JOIN active USING (taxonomy_version, derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.metric_estimates_v2 AS legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM active
    WHERE active.taxonomy_version = legacy.taxonomy_version
);

CREATE OR REPLACE VIEW mart_.macro_family_weekly_v2_production AS
WITH active AS (
    SELECT taxonomy_version, derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v2'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.macro_family_weekly_v2_versioned AS versioned
INNER JOIN active USING (taxonomy_version, derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.macro_family_weekly_v2 AS legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM active
    WHERE active.taxonomy_version = legacy.taxonomy_version
);

CREATE OR REPLACE VIEW mart_.ecosystem_weekly_v2_production AS
WITH active AS (
    SELECT taxonomy_version, derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v2'
        AND validation_status = 'validated'
        AND is_active
)
SELECT versioned.* EXCLUDE (derivation_version)
FROM mart_.ecosystem_weekly_v2_versioned AS versioned
INNER JOIN active USING (taxonomy_version, derivation_version)

UNION ALL

SELECT legacy.*
FROM mart_.ecosystem_weekly_v2 AS legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM active
    WHERE active.taxonomy_version = legacy.taxonomy_version
);

CREATE OR REPLACE VIEW mart_.lastfm_listening_windows_production AS
SELECT windows.*
FROM mart_.lastfm_listening_windows AS windows
INNER JOIN mart_.metric_artifact_versions AS active
    ON active.artifact_family = windows.artifact_family
    AND active.taxonomy_version = windows.taxonomy_version
    AND active.derivation_version = windows.derivation_version
    AND active.validation_status = 'validated'
    AND active.is_active;
