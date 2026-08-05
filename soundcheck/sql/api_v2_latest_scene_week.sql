SELECT max(as_of_week)
FROM mart_.scene_map_v2
WHERE taxonomy_version = ? AND context = ?;
