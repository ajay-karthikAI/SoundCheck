INSERT INTO mart_.pipeline_runs (
    run_id,
    run_kind,
    trigger_name,
    git_sha,
    status,
    started_at
)
VALUES (?, ?, ?, ?, 'running', ?)
ON CONFLICT (run_id) DO UPDATE SET
    run_kind = excluded.run_kind,
    trigger_name = excluded.trigger_name,
    git_sha = excluded.git_sha,
    status = 'running',
    started_at = excluded.started_at,
    completed_at = NULL,
    wall_time_seconds = NULL,
    bluesky_posts_ingested = 0,
    bluesky_engagement_snapshots_ingested = 0,
    lastfm_tag_snapshots_ingested = 0,
    lastfm_artist_snapshots_ingested = 0,
    musicbrainz_release_groups_ingested = 0,
    resolution_posts_attempted = 0,
    resolution_links_resolved = 0,
    resolution_rate = NULL,
    metric_rows = 0,
    forecast_rows = 0,
    brief_rows = 0,
    error_message = NULL;
