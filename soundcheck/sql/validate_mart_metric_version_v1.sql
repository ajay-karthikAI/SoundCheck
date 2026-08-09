WITH invalid_windows AS (
    SELECT count(*) AS failures
    FROM mart_.lastfm_listening_windows
    WHERE
        artifact_family = 'v1'
        AND taxonomy_version = 'v1'
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
    FROM mart_.genre_weekly_versioned AS metric
    WHERE
        metric.derivation_version = ?
        AND (metric.opportunity IS NOT NULL OR metric.discovery_gap IS NOT NULL)
        AND NOT EXISTS (
            SELECT 1
            FROM mart_.lastfm_listening_windows AS audit
            WHERE
                audit.artifact_family = 'v1'
                AND audit.taxonomy_version = 'v1'
                AND audit.derivation_version = metric.derivation_version
                AND audit.week_start = metric.week_start
                AND lower(audit.genre_id) = lower(metric.canonical_genre)
                AND audit.listening_window_status = 'valid_weekly'
        )
)
SELECT invalid_windows.failures + invalid_claims.failures
FROM invalid_windows, invalid_claims;
