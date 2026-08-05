SELECT
    (SELECT count(*) FROM stg_.tag_genre_map) AS mapping_count,
    (
        SELECT count(*)
        FROM stg_.canonical_genre_embeddings
    ) AS embedding_count;

