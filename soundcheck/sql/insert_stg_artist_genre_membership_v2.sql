INSERT INTO stg_.artist_genre_memberships_v2 (
    artist_key_type,
    artist_key,
    artist_mbid,
    artist_name,
    canonical_genre_id,
    macro_family_id,
    parent_genre_id,
    membership_weight,
    method,
    confidence,
    source_systems,
    source_tags,
    input_fingerprint,
    taxonomy_version,
    resolved_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
