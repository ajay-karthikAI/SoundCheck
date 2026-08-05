SELECT
    run_id,
    run_kind,
    trigger_name,
    git_sha,
    status,
    started_at,
    completed_at,
    wall_time_seconds,
    bluesky_posts_ingested,
    bluesky_engagement_snapshots_ingested,
    lastfm_tag_snapshots_ingested,
    lastfm_artist_snapshots_ingested,
    musicbrainz_release_groups_ingested,
    resolution_posts_attempted,
    resolution_links_resolved,
    resolution_rate,
    metric_rows,
    forecast_rows,
    brief_rows,
    error_message
FROM mart_.pipeline_runs
WHERE run_id = ?;
