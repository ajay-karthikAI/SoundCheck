SELECT
    genre_id,
    macro_family_id,
    count(*) FILTER (WHERE estimate_eligible) AS valid_metric_weeks,
    count(*) AS observed_weeks
FROM mart_.genre_weekly_v2
WHERE taxonomy_version = ?
GROUP BY genre_id, macro_family_id
ORDER BY macro_family_id, genre_id;
