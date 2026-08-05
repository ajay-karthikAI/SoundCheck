WITH latest_week AS (
    SELECT max(week_start) AS week_start
    FROM mart_.genre_coverage_v2
    WHERE taxonomy_version = ?
)
SELECT
    coverage.week_start,
    coverage.genre_id,
    coverage.display_name,
    coverage.macro_family_id,
    coverage.macro_family_name,
    coverage.taxonomy_status,
    coverage.eligibility_state,
    coverage.cross_source_overlap,
    coverage.listening_missing,
    coverage.conversation_missing,
    coverage.supply_missing,
    coverage.latest_source_timestamp,
    coverage.stale
FROM mart_.genre_coverage_v2 AS coverage
JOIN latest_week USING (week_start)
WHERE coverage.taxonomy_version = ?
ORDER BY coverage.macro_family_id, coverage.genre_id;
