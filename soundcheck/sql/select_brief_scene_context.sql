SELECT
    embedding.canonical_genre,
    embedding.embedding,
    metric.supply_index,
    metric.supply_release_groups
FROM stg_.canonical_genre_embeddings AS embedding
INNER JOIN mart_.genre_weekly_production AS metric
    ON
        metric.canonical_genre = embedding.canonical_genre
        AND metric.week_start = ?
ORDER BY embedding.canonical_genre;
