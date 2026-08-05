SELECT
    macro_family_id,
    status,
    production_eligible,
    labeled_examples,
    precision,
    recall,
    mbid_precision,
    reasons,
    taxonomy_version
FROM stg_.genre_family_activation_v2
WHERE taxonomy_version = ?
ORDER BY macro_family_id;
