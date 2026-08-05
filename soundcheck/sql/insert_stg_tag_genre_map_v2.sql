INSERT INTO stg_.tag_genre_map_v2 (
    source_system,
    source_tag,
    normalized_source_tag,
    canonical_genre_id,
    macro_family_id,
    parent_genre_id,
    membership_weight,
    method,
    confidence,
    language,
    model_name,
    taxonomy_version,
    resolved_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (
    taxonomy_version,
    source_system,
    normalized_source_tag,
    canonical_genre_id
) DO NOTHING;
