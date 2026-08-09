SELECT count(*)
FROM mart_.metric_row_withdrawals
WHERE
    artifact_family = ?
    AND taxonomy_version = ?
    AND derivation_version = ?;
