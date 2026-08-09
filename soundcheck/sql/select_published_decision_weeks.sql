SET TimeZone = 'UTC';

SELECT
    (
        SELECT max(week_start)
        FROM mart_.genre_weekly_production
        WHERE opportunity IS NOT NULL
    ) AS v1_week,
    (
        SELECT max(week_start)
        FROM mart_.metric_estimates_v2_production
        WHERE
            taxonomy_version = ?
            AND scope_type = 'genre'
            AND context = 'global'
            AND metric_name = 'opportunity'
            AND estimate IS NOT NULL
    ) AS v2_week;
