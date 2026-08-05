SELECT
    source_system,
    source_tag,
    normalized_source_tag,
    list(
        canonical_genre_id
        ORDER BY membership_weight DESC, canonical_genre_id
    ) AS predicted_genre_ids,
    first(method ORDER BY membership_weight DESC, canonical_genre_id) AS method,
    first(
        macro_family_id
        ORDER BY membership_weight DESC, canonical_genre_id
    ) AS macro_family_id,
    first(language ORDER BY membership_weight DESC, canonical_genre_id) AS language
FROM stg_.tag_genre_map_v2
WHERE taxonomy_version = ?
GROUP BY source_system, source_tag, normalized_source_tag
ORDER BY source_system, normalized_source_tag;
