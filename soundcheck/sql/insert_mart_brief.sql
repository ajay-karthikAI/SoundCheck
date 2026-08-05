INSERT INTO mart_.briefs (
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
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
