WITH recent AS (
    SELECT
        week_start,
        canonical_genre,
        conversation_index,
        conversation_index_ci_low,
        conversation_index_ci_high,
        conversation_ewma,
        conversation_ewma_ci_low,
        conversation_ewma_ci_high,
        conversation_spike,
        listening_index,
        listening_index_ci_low,
        listening_index_ci_high,
        listening_ewma,
        listening_ewma_ci_low,
        listening_ewma_ci_high,
        listening_spike,
        supply_index,
        supply_index_ci_low,
        supply_index_ci_high,
        supply_ewma,
        supply_ewma_ci_low,
        supply_ewma_ci_high,
        supply_spike,
        opportunity,
        opportunity_ci_low,
        opportunity_ci_high,
        discovery_gap,
        discovery_gap_ci_low,
        discovery_gap_ci_high
    FROM mart_.genre_weekly
    WHERE lower(canonical_genre) = lower(?)
    ORDER BY week_start DESC
    LIMIT ?
)
SELECT *
FROM recent
ORDER BY week_start;
