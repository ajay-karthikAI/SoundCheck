INSERT INTO stg_.collection_checkpoints (
    source,
    run_key,
    phase,
    unit_key,
    shard_index,
    payload_json,
    completed_at
)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source, run_key, phase, unit_key) DO NOTHING;
