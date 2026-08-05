SET TimeZone = 'UTC';

SELECT
    metric.week_start,
    metric.canonical_genre,
    metric.conversation_index,
    metric.listening_index,
    metric.supply_index,
    metric.supply_index_ci_low,
    metric.supply_index_ci_high,
    metric.discovery_gap,
    metric.conversation_ewma,
    metric.listening_ewma,
    metric.supply_ewma,
    metric.conversation_spike,
    metric.listening_spike,
    metric.supply_spike,
    metric.opportunity,
    metric.opportunity_ci_low,
    metric.opportunity_ci_high,
    metric.breakout_precursor,
    coalesce(embedding.embedding, []::FLOAT[]) AS genre_embedding
FROM mart_.genre_weekly AS metric
LEFT JOIN stg_.canonical_genre_embeddings AS embedding
    ON embedding.canonical_genre = metric.canonical_genre
ORDER BY metric.week_start, metric.canonical_genre;
