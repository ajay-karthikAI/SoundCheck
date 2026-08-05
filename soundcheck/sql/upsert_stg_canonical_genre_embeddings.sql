INSERT INTO stg_.canonical_genre_embeddings (
    canonical_genre,
    embedding,
    model_name,
    embedded_at
)
VALUES (?, ?, ?, ?)
ON CONFLICT (canonical_genre) DO UPDATE SET
    embedding = excluded.embedding,
    model_name = excluded.model_name,
    embedded_at = excluded.embedded_at;

