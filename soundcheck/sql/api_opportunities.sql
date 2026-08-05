SELECT
    week_start,
    canonical_genre,
    opportunity,
    opportunity_ci_low,
    opportunity_ci_high,
    discovery_gap,
    discovery_gap_ci_low,
    discovery_gap_ci_high,
    conversation_index,
    conversation_index_ci_low,
    conversation_index_ci_high,
    listening_index,
    listening_index_ci_low,
    listening_index_ci_high,
    supply_index,
    supply_index_ci_low,
    supply_index_ci_high,
    conversation_shrinkage_weight,
    supply_shrinkage_weight,
    conversation_effective_n,
    supply_effective_n,
    conversation_spike,
    listening_spike,
    supply_spike,
    breakout_precursor
FROM mart_.genre_weekly
WHERE
    week_start = ?
    AND opportunity IS NOT NULL
ORDER BY opportunity DESC, canonical_genre
LIMIT ?;
