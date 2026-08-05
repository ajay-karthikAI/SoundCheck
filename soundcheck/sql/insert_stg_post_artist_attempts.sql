INSERT INTO stg_.post_artist_resolution_attempts (
    post_uri,
    outcome,
    candidate_count,
    attempted_at
)
VALUES (?, ?, ?, ?)
ON CONFLICT (post_uri) DO UPDATE SET
    outcome = excluded.outcome,
    candidate_count = excluded.candidate_count,
    attempted_at = excluded.attempted_at;
