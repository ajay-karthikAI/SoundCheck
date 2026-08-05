INSERT INTO mart_.scene_map (
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
    evidence_volume,
    computed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
