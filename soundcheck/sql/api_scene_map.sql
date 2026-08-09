WITH latest_complete AS (
    SELECT max(week_start) AS week_start
    FROM mart_.genre_weekly_production
    WHERE
        opportunity IS NOT NULL
        AND week_start < CAST(date_trunc('week', current_timestamp) AS DATE)
),
coordinates AS (
    SELECT canonical_genre, x, y
    FROM mart_.scene_map
    QUALIFY row_number() OVER (
        PARTITION BY canonical_genre
        ORDER BY as_of_week DESC
    ) = 1
)
SELECT
    metric.week_start AS as_of_week,
    metric.canonical_genre,
    coordinates.x,
    coordinates.y,
    metric.opportunity,
    metric.opportunity_ci_low,
    metric.opportunity_ci_high,
    metric.discovery_gap,
    metric.discovery_gap_ci_low,
    metric.discovery_gap_ci_high,
    len(metric.conversation_post_uris)
        + len(metric.listening_artist_keys)
        + len(metric.supply_release_group_mbids) AS evidence_volume
FROM mart_.genre_weekly_production AS metric
INNER JOIN latest_complete USING (week_start)
INNER JOIN coordinates USING (canonical_genre)
ORDER BY metric.canonical_genre;
