SELECT
    (
        SELECT count(*)
        FROM raw_.bluesky_posts
        WHERE ingested_at >= ? AND ingested_at <= ?
    ) AS bluesky_posts_ingested,
    (
        SELECT count(*)
        FROM raw_.bluesky_engagement
        WHERE fetched_at >= ? AND fetched_at <= ?
    ) AS bluesky_engagement_snapshots_ingested,
    (
        SELECT count(*)
        FROM raw_.lastfm_tag_snapshots
        WHERE fetched_at >= ? AND fetched_at <= ?
    ) AS lastfm_tag_snapshots_ingested,
    (
        SELECT count(*)
        FROM raw_.lastfm_artist_snapshots
        WHERE fetched_at >= ? AND fetched_at <= ?
    ) AS lastfm_artist_snapshots_ingested,
    (
        SELECT count(*)
        FROM raw_.mb_release_groups
        WHERE fetched_at >= ? AND fetched_at <= ?
    ) AS musicbrainz_release_groups_ingested,
    (
        SELECT count(DISTINCT post_uri)
        FROM stg_.post_artist_resolution_attempts
        WHERE attempted_at >= ? AND attempted_at <= ?
    ) AS resolution_posts_attempted,
    (
        SELECT count(DISTINCT post_uri)
        FROM stg_.post_artist_links
        WHERE resolved_at >= ? AND resolved_at <= ?
    ) AS resolution_links_resolved,
    (
        SELECT count(*)
        FROM mart_.genre_weekly
        WHERE computed_at >= ? AND computed_at <= ?
    ) AS metric_rows,
    (
        SELECT count(*)
        FROM fcst_.predictions
        WHERE created_at >= ? AND created_at <= ?
    ) AS forecast_rows,
    (
        SELECT count(*)
        FROM mart_.briefs
        WHERE created_at >= ? AND created_at <= ?
    ) AS brief_rows;
