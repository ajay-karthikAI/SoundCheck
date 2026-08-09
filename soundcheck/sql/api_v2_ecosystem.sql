WITH recent AS (
    SELECT *
    FROM mart_.ecosystem_weekly_v2_production
    WHERE
        taxonomy_version = ?
        AND week_start < CAST(date_trunc('week', current_timestamp) AS DATE)
        AND estimate_status = 'ready'
        AND (
            (? = 'global' AND scope_type = 'global')
            OR (
                ? = 'peer_family'
                AND scope_type = 'macro_family'
                AND (? IS NULL OR scope_id = ?)
            )
        )
    ORDER BY week_start DESC, scope_id
    LIMIT ?
)
SELECT *
FROM recent
ORDER BY week_start, scope_id;
