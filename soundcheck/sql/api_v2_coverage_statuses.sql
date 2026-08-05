SELECT genre_id, eligibility_state
FROM mart_.genre_coverage_v2
WHERE taxonomy_version = ? AND week_start = ?
ORDER BY genre_id;
