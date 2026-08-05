SELECT
    shard_index,
    payload_json,
    completed_at
FROM stg_.collection_checkpoints
WHERE source = ?
  AND run_key = ?
  AND phase = ?
  AND unit_key = ?;
