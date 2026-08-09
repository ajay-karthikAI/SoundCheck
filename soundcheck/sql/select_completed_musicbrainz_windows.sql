SELECT
    try_cast(json_extract_string(metadata.payload_json, '$.window_start') AS DATE),
    try_cast(json_extract_string(metadata.payload_json, '$.window_end') AS DATE),
    completed.completed_at
FROM stg_.collection_checkpoints AS metadata
JOIN stg_.collection_checkpoints AS completed
    ON completed.source = metadata.source
    AND completed.run_key = metadata.run_key
    AND completed.phase = 'run'
    AND completed.unit_key = 'completed'
WHERE
    metadata.source = 'musicbrainz'
    AND metadata.phase = 'run'
    AND metadata.unit_key = 'metadata'
    AND try_cast(
        json_extract_string(metadata.payload_json, '$.window_start') AS DATE
    ) IS NOT NULL
    AND try_cast(
        json_extract_string(metadata.payload_json, '$.window_end') AS DATE
    ) IS NOT NULL
ORDER BY 1, 2, 3;
