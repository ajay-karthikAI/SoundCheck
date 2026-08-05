SELECT
    source_system,
    raw_tag,
    canonical_genre,
    method,
    similarity
FROM stg_.tag_genre_map
ORDER BY source_system, raw_tag;
