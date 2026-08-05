SELECT canonical_genre_id
FROM stg_.canonical_genre_embeddings_v2
WHERE taxonomy_version = ? AND model_name = ?
ORDER BY canonical_genre_id;
