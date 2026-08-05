INSERT INTO stg_.tag_genre_map (
    source_system,
    raw_tag,
    canonical_genre,
    similarity,
    method,
    model_name,
    resolved_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source_system, raw_tag) DO UPDATE SET
    canonical_genre = excluded.canonical_genre,
    similarity = excluded.similarity,
    method = excluded.method,
    model_name = excluded.model_name,
    resolved_at = excluded.resolved_at;

