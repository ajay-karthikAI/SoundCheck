DELETE FROM mart_.genre_weekly_v2_versioned
WHERE taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.metric_estimates_v2_versioned
WHERE taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.macro_family_weekly_v2_versioned
WHERE taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.ecosystem_weekly_v2_versioned
WHERE taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.lastfm_listening_windows
WHERE artifact_family = 'v2' AND taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.metric_row_withdrawals
WHERE artifact_family = 'v2' AND taxonomy_version = ? AND derivation_version = ?;
DELETE FROM mart_.metric_artifact_versions
WHERE artifact_family = 'v2' AND taxonomy_version = ? AND derivation_version = ?;
