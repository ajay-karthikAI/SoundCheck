SELECT
    source_system,
    source_tag,
    normalized_source_tag,
    canonical_genre_id,
    macro_family_id,
    method,
    confidence,
    membership_weight
FROM stg_.tag_genre_map_v2
WHERE taxonomy_version = ?
ORDER BY
    source_system,
    normalized_source_tag,
    canonical_genre_id;
