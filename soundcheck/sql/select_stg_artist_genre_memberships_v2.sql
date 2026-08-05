SELECT
    artist_key,
    canonical_genre_id,
    macro_family_id,
    parent_genre_id,
    membership_weight,
    taxonomy_version
FROM stg_.artist_genre_memberships_v2
WHERE taxonomy_version = ?
ORDER BY artist_key, canonical_genre_id;
