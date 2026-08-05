SELECT max(week_start)
FROM mart_.genre_coverage_v2
WHERE taxonomy_version = ?;
