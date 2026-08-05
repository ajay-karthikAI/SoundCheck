INSERT INTO stg_.post_artist_ambiguities (
    post_uri,
    artist_name_raw,
    top_artist_mbid,
    top_artist_name,
    top_score,
    second_artist_mbid,
    second_artist_name,
    second_score,
    reason,
    resolved_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (post_uri, artist_name_raw) DO UPDATE SET
    top_artist_mbid = excluded.top_artist_mbid,
    top_artist_name = excluded.top_artist_name,
    top_score = excluded.top_score,
    second_artist_mbid = excluded.second_artist_mbid,
    second_artist_name = excluded.second_artist_name,
    second_score = excluded.second_score,
    reason = excluded.reason,
    resolved_at = excluded.resolved_at;

