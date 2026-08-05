SELECT max(week_start)
FROM mart_.metric_estimates_v2
WHERE
    taxonomy_version = ?
    AND scope_type = 'genre'
    AND context = ?
    AND metric_name = 'opportunity'
    AND estimate IS NOT NULL;
