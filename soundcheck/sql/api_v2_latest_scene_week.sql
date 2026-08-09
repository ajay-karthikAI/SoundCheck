SELECT max(week_start)
FROM mart_.metric_estimates_v2_production
WHERE
    taxonomy_version = ?
    AND context = ?
    AND scope_type = 'genre'
    AND metric_name = 'opportunity'
    AND estimate IS NOT NULL
    AND week_start < CAST(date_trunc('week', current_timestamp) AS DATE);
