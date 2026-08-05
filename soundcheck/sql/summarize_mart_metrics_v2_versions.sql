SELECT
    taxonomy_version,
    count(*) AS genre_week_rows
FROM mart_.genre_weekly_v2
GROUP BY taxonomy_version
ORDER BY taxonomy_version;
