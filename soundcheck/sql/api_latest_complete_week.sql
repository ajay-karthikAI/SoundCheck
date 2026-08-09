SET TimeZone = 'UTC';

SELECT max(week_start)
FROM mart_.genre_weekly_production
WHERE
    opportunity IS NOT NULL
    AND week_start < CAST(date_trunc('week', current_timestamp) AS DATE)
    AND week_start < CAST(date_trunc('week', current_date) AS DATE);
