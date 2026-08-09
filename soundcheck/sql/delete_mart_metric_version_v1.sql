DELETE FROM mart_.genre_weekly_versioned WHERE derivation_version = ?;
DELETE FROM mart_.ecosystem_weekly_versioned WHERE derivation_version = ?;
DELETE FROM mart_.lastfm_listening_windows
WHERE artifact_family = 'v1' AND taxonomy_version = 'v1' AND derivation_version = ?;
DELETE FROM mart_.metric_row_withdrawals
WHERE artifact_family = 'v1' AND taxonomy_version = 'v1' AND derivation_version = ?;
DELETE FROM mart_.metric_artifact_versions
WHERE artifact_family = 'v1' AND taxonomy_version = 'v1' AND derivation_version = ?;
