WITH active AS (
    SELECT derivation_version
    FROM mart_.metric_artifact_versions
    WHERE
        artifact_family = 'v2'
        AND taxonomy_version = ?
        AND validation_status = 'validated'
        AND is_active
),
evidence AS (
    SELECT
        audit.artist_key,
        audit.artist_name,
        audit.artist_mbid,
        audit.playcount,
        audit.listeners,
        audit.previous_playcount,
        audit.previous_listeners,
        audit.playcount - audit.previous_playcount AS playcount_delta,
        audit.listeners - audit.previous_listeners AS listeners_delta,
        audit.fetched_at,
        audit.previous_fetched_at,
        audit.interval_days,
        audit.listening_window_status,
        audit.membership_weight,
        audit.membership_method,
        audit.membership_confidence
    FROM mart_.lastfm_listening_windows AS audit
    INNER JOIN active USING (derivation_version)
    WHERE
        audit.artifact_family = 'v2'
        AND audit.taxonomy_version = ?
        AND audit.genre_id = ?
        AND audit.week_start = ?
        AND audit.listening_window_status = 'valid_weekly'

    UNION ALL

    SELECT
        legacy.artist_key,
        legacy.artist_name,
        legacy.artist_mbid,
        legacy.playcount,
        legacy.listeners,
        legacy.previous_playcount,
        legacy.previous_listeners,
        legacy.playcount_delta,
        legacy.listeners_delta,
        legacy.fetched_at,
        legacy.previous_fetched_at,
        date_diff('second', legacy.previous_fetched_at, legacy.fetched_at)
            / 86400.0,
        'legacy_unvalidated',
        legacy.membership_weight,
        legacy.membership_method,
        legacy.membership_confidence
    FROM mart_.listening_evidence_v2 AS legacy
    WHERE
        NOT EXISTS (SELECT 1 FROM active)
        AND legacy.taxonomy_version = ?
        AND legacy.genre_id = ?
        AND legacy.week_start = ?
)
SELECT *
FROM evidence
ORDER BY artist_key
LIMIT ? OFFSET ?;
