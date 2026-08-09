UPDATE mart_.metric_artifact_versions
SET is_active = false
WHERE artifact_family = ? AND taxonomy_version = ?;

INSERT INTO mart_.metric_artifact_versions (
    artifact_family,
    taxonomy_version,
    derivation_version,
    validation_status,
    is_active,
    validated_at,
    withdrawal_count
)
VALUES (?, ?, ?, 'validated', true, ?, ?);
