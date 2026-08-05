SELECT
    source_system,
    raw_tag,
    canonical_genre,
    similarity,
    method,
    model_name,
    resolved_at
FROM stg_.tag_genre_map
ORDER BY source_system, raw_tag;

