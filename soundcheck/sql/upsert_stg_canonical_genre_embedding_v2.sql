INSERT INTO stg_.canonical_genre_embeddings_v2 (
    canonical_genre_id,
    macro_family_id,
    parent_genre_id,
    embedding,
    model_name,
    taxonomy_version,
    embedded_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (taxonomy_version, canonical_genre_id) DO UPDATE SET
    macro_family_id = excluded.macro_family_id,
    parent_genre_id = excluded.parent_genre_id,
    embedding = excluded.embedding,
    model_name = excluded.model_name,
    embedded_at = excluded.embedded_at;
