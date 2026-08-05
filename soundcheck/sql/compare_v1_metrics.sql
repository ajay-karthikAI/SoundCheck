SELECT
    week_start,
    canonical_genre,
    opportunity,
    discovery_gap,
    listening_index IS NULL AS listening_missing,
    opportunity IS NULL AS opportunity_missing
FROM mart_.genre_weekly
ORDER BY week_start, canonical_genre;
