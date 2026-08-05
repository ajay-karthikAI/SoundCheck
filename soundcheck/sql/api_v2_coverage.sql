SELECT
    coverage.genre_id,
    coverage.eligibility_state,
    coverage.week_start,
    coverage.lastfm_tag_available,
    coverage.unique_lastfm_artists,
    coverage.artists_with_consecutive_valid_snapshots,
    coverage.lastfm_history_weeks,
    coverage.musicbrainz_release_group_count,
    coverage.resolved_bluesky_post_count,
    coverage.resolution_attempt_count,
    coverage.resolution_rate,
    coverage.cross_source_overlap_artist_count,
    coverage.cross_source_overlap,
    coverage.latest_source_timestamp,
    coverage.listening_missing,
    coverage.conversation_missing,
    coverage.supply_missing,
    coverage.stale
FROM mart_.genre_coverage_v2 AS coverage
LEFT JOIN mart_.genre_weekly_v2 AS genre
    ON genre.taxonomy_version = coverage.taxonomy_version
    AND genre.week_start = coverage.week_start
    AND genre.genre_id = coverage.genre_id
WHERE
    coverage.taxonomy_version = ?
    AND coverage.week_start = ?
    AND (? IS NULL OR coverage.macro_family_id = ?)
    AND (? IS NULL OR genre.parent_genre_id = ?)
    AND (? IS NULL OR coverage.eligibility_state = ?)
ORDER BY coverage.genre_id
LIMIT ? OFFSET ?;
