WITH invalid_windows AS (
    SELECT count(*) AS failures
    FROM mart_.lastfm_listening_windows
    WHERE
        artifact_family = 'v2'
        AND taxonomy_version = ?
        AND derivation_version = ?
        AND listening_window_status = 'valid_weekly'
        AND (
            NOT observations_append_only
            OR previous_fetched_at IS NULL
            OR fetched_at <= previous_fetched_at
            OR date_trunc('week', fetched_at)
                <> date_trunc('week', previous_fetched_at) + INTERVAL 7 DAY
            OR playcount < previous_playcount
            OR listeners < previous_listeners
        )
),
invalid_claims AS (
    SELECT count(*) AS failures
    FROM mart_.metric_estimates_v2_versioned AS metric
    WHERE
        metric.taxonomy_version = ?
        AND metric.derivation_version = ?
        AND metric.scope_type = 'genre'
        AND metric.metric_name IN ('opportunity', 'discovery_gap')
        AND metric.estimate IS NOT NULL
        AND NOT EXISTS (
            SELECT 1
            FROM mart_.lastfm_listening_windows AS audit
            WHERE
                audit.artifact_family = 'v2'
                AND audit.taxonomy_version = metric.taxonomy_version
                AND audit.derivation_version = metric.derivation_version
                AND audit.week_start = metric.week_start
                AND audit.genre_id = metric.scope_id
                AND audit.listening_window_status = 'valid_weekly'
        )
)
SELECT invalid_windows.failures + invalid_claims.failures
FROM invalid_windows, invalid_claims;
