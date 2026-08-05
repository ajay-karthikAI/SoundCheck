SELECT count(*)
FROM raw_.mb_release_groups
WHERE try_cast(first_release_date AS DATE) BETWEEN ? AND ?;
