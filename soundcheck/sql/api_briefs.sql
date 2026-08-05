SELECT
    brief_id,
    week_start,
    canonical_genre,
    headline,
    opportunity,
    opportunity_ci_low,
    opportunity_ci_high,
    rationale,
    recommended_actions,
    evidence_uris,
    created_at
FROM mart_.briefs
WHERE week_start = ?
ORDER BY opportunity DESC, canonical_genre;
