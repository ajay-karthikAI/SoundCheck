WITH active AS (
    SELECT derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v1'
        AND taxonomy_version = 'v1'
        AND validation_status = 'validated'
        AND is_active
),
evidence AS (
    SELECT
        audit.artist_key,
        audit.artist_name,
        audit.artist_mbid,
        audit.playcount - audit.previous_playcount AS playcount_delta,
        audit.listeners - audit.previous_listeners AS listeners_delta,
        audit.previous_fetched_at,
        audit.fetched_at,
        audit.interval_days,
        audit.listening_window_status,
        (
            audit.playcount - audit.previous_playcount
            + 5 * (audit.listeners - audit.previous_listeners)
        ) AS weighted_delta
    FROM mart_.lastfm_listening_windows AS audit
    INNER JOIN active USING (derivation_version)
    WHERE
        audit.artifact_family = 'v1'
        AND audit.taxonomy_version = 'v1'
        AND lower(audit.genre_id) = lower(?)
        AND audit.week_start = ?
        AND audit.listening_window_status = 'valid_weekly'

    UNION ALL

    SELECT
        legacy.artist_key,
        legacy.artist_name,
        legacy.artist_mbid,
        legacy.playcount_delta,
        legacy.listeners_delta,
        NULL,
        legacy.fetched_at,
        NULL,
        'legacy_unvalidated',
        legacy.weighted_delta
    FROM mart_.listening_evidence AS legacy
    WHERE
        NOT EXISTS (SELECT 1 FROM active)
        AND lower(legacy.canonical_genre) = lower(?)
        AND legacy.week_start = ?
)
SELECT * EXCLUDE (weighted_delta)
FROM evidence
ORDER BY weighted_delta DESC, artist_key
LIMIT ?;
