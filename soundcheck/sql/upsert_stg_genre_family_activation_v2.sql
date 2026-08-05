INSERT INTO stg_.genre_family_activation_v2 (
    macro_family_id,
    status,
    production_eligible,
    labeled_examples,
    precision,
    recall,
    mbid_precision,
    reasons,
    taxonomy_version,
    evaluated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (taxonomy_version, macro_family_id) DO UPDATE SET
    status = excluded.status,
    production_eligible = excluded.production_eligible,
    labeled_examples = excluded.labeled_examples,
    precision = excluded.precision,
    recall = excluded.recall,
    mbid_precision = excluded.mbid_precision,
    reasons = excluded.reasons,
    evaluated_at = excluded.evaluated_at;
