SELECT
    unit_key,
    shard_index,
    payload_json,
    completed_at
FROM stg_.collection_checkpoints
WHERE source = ?
  AND run_key = ?
  AND phase = ?
ORDER BY unit_key;
