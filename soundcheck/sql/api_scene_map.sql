SELECT
    as_of_week,
    canonical_genre,
    x,
    y,
    opportunity,
    opportunity_ci_low,
    opportunity_ci_high,
    discovery_gap,
    discovery_gap_ci_low,
    discovery_gap_ci_high,
    evidence_volume
FROM mart_.scene_map
WHERE as_of_week = (SELECT max(as_of_week) FROM mart_.scene_map)
ORDER BY canonical_genre;
