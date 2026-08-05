SELECT max(week_start)
FROM mart_.briefs_v2
WHERE taxonomy_version = ? AND context = ?;
