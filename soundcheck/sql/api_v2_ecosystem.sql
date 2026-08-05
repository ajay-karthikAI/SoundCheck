WITH recent AS (
    SELECT *
    FROM mart_.ecosystem_weekly_v2
    WHERE
        taxonomy_version = ?
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
