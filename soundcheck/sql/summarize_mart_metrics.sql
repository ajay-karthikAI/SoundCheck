SELECT
    (SELECT count(*) FROM mart_.genre_weekly) AS genre_week_count,
    (SELECT count(*) FROM mart_.ecosystem_weekly) AS ecosystem_week_count;
