SELECT
    genre_id,
    coverage_status,
    as_of_week,
    context,
    x,
    y,
    opportunity,
    opportunity_ci_low,
    opportunity_ci_high,
    discovery_gap,
    discovery_gap_ci_low,
    discovery_gap_ci_high,
    evidence_volume
FROM mart_.scene_map_v2
WHERE
    taxonomy_version = ?
    AND as_of_week = ?
    AND context = ?
    AND (? IS NULL OR macro_family_id = ?)
    AND (? IS NULL OR parent_genre_id = ?)
    AND (? IS NULL OR coverage_status = ?)
ORDER BY genre_id
LIMIT ? OFFSET ?;
