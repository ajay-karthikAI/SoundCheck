# Soundcheck Repository Instructions

This file governs the entire repository. Every rule below is a permanent
invariant for all sessions and all contributors. Do not weaken, bypass, or
silently reinterpret these requirements. If a proposed feature conflicts with
an invariant, preserve the invariant and cut or redesign the feature.

## Product Mission

Soundcheck is a live, genre-neutral music trend-intelligence product with an
indie-focused default view. It serves music-platform data, editorial,
creator-success, and ecosystem-health teams by fusing:

- music conversation from Bluesky;
- listening change from Last.fm; and
- release supply from MusicBrainz

to produce opportunity scores, discovery-gap analysis, validated weekly
forecasts, and generated creator briefs. Genre-neutral describes the product's
scope, not a claim of universal source coverage. A genre becomes
decision-ready only after its cross-source evidence clears published coverage
and resolution gates.

## Product Principles

- Treat Soundcheck as a product, not a dashboard. Every surface must answer a
  question a music-platform data, editorial, creator-success, or
  ecosystem-health team actually asks:
  - Where is attention outrunning supply?
  - What will move next week?
  - Is the ecosystem healthy?
  - What should a creator make?
- Be evidence-first. Every score must link to the raw posts, artists, and
  releases that produced it. Numbers without receipts do not ship.
- Represent uncertainty honestly. Every user-facing estimate must carry a
  confidence interval or a published backtest error. State explicitly what the
  product does not know.
- Treat source coverage as part of the result. A genre without adequate
  conversation, listening-change, and release-supply evidence must be marked
  `insufficient_evidence`; missing evidence must never be displayed as zero
  activity.
- Keep indie music as the default discovery lens while allowing every enabled,
  evidence-qualified genre to use the same product questions and rigor. Do not
  treat the default view as a different statistical standard.
- Keep the product self-updating. It must refresh weekly through scheduled
  automation with zero manual steps. A stale product is a dead product.

## The Three Axes

### Music Conversation

- Use Bluesky public Jetstream and AppView.
- Use no authentication and no private data.

### Listening Change

- Use the Last.fm API.
- Read its API key from `LASTFM_API_KEY`.
- Limit requests to 4 requests per second.
- Apply backoff and use a disk cache.

### Release Supply

- Use the MusicBrainz API.
- Enforce its strict 1-request-per-second limit.
- Send a descriptive `User-Agent`.
- Cache responses.

## Architecture

- Use Python 3.12 for all data work.
- Build async-first integrations with `httpx.AsyncClient` and `websockets`.
- Use DuckDB as the only datastore.
- Use these DuckDB schema prefixes and responsibilities:
  - `raw_`: append-only source data;
  - `stg_`: resolved and staged entities;
  - `mart_`: genre-week aggregates; and
  - `fcst_`: forecasts and backtest scores.
- Keep FastAPI as a thin, read-only layer over `mart_` and `fcst_`.
  Endpoints must not compute metrics, models, or aggregates. All mathematics
  belongs in the batch pipeline.
- Build the frontend with Next.js 14 App Router and TypeScript.
- The frontend must consume only the frozen contract in
  `docs/api_contract.md`.
- The frontend must never access DuckDB directly.
- Run the weekly batch through a GitHub Actions cron in this exact dependency
  order:

  `ingest -> resolve -> metrics -> forecast -> briefs -> publish artifact -> deploy`

## Permanent Constraints

- Do not scrape. Use official, documented APIs only. Cut any feature that
  requires scraping.
- Do not introduce paid APIs or paid-account prerequisites.
- SoundCloud is rejected because app registration requires an Artist Pro
  paywall.
- Bandcamp is rejected because it has no official API.
- Keep both rejections documented in `docs/data_provenance.md`.
- Store and process all timestamps in UTC.
- Use ISO weeks for every aggregation window.

## Critical Last.fm Data-Modeling Rule

Last.fm exposes cumulative lifetime totals, not listening events. Therefore:

- Derive every listening metric from deltas between append-only snapshots
  keyed by `fetched_at`.
- Never overwrite a snapshot.
- Never treat a lifetime playcount as a weekly signal.
- Exclude first observations from delta metrics; never zero-fill them.

This rule is load-bearing. Do not "fix," relax, or reinterpret it in a later
session.

## Code Standards and Quality Gates

- `ruff` must be green before any phase closes.
- `mypy` in strict mode must be green before any phase closes.
- The full `pytest` suite must be green at every gate.
- Use Pydantic v2 at every input/output boundary.
- Put SQL in `.sql` files under `sql/` and load it by name.
- Do not use f-string SQL or construct SQL through string interpolation.
- Do not use pandas in the serving path.
- A phase is not complete while any applicable lint, type-check, or test gate
  is failing.

## Statistical Invariants

- Do not show a point estimate on a user-facing surface without uncertainty.
- Do not publish a genre estimate until its documented cross-source coverage
  gate passes. Use `insufficient_evidence`, not a zero-filled estimate, when
  the gate fails.
- Apply empirical Bayes shrinkage to small-sample genres toward the weekly
  cross-genre prior.
- Derive and maintain the shrinkage formulas in `docs/metrics.md`.
- Z-score all indices within each week, never globally.
- Publish forecasts only alongside their backtested skill scores.
- If a forecast cannot beat the naive baseline, display it as `no skill`.
  Never hide it merely because it lacks skill.

## Required Project Structure

Maintain the following top-level structure:

```text
soundcheck/
  ingest/
    bluesky/
    lastfm/
    musicbrainz/
  resolve/
  metrics/
  forecast/
  briefs/
  sql/
  api/
  web/
  docs/
    metrics.md
    forecasting.md
    product_scope_v2.md
    taxonomy.md
    experiment_design.md
    data_provenance.md
    api_contract.md
  .github/
    workflows/
  tests/
  scripts/
```

Add files within this structure as needed, but do not collapse the separation
between ingestion, resolution, metrics, forecasting, briefs, serving, and the
frontend.

## Change Review Checklist

Before considering any change complete, verify that:

1. The change answers a concrete product question rather than merely exposing
   data.
2. Every derived user-facing number has evidence links and uncertainty.
3. Last.fm listening signals use snapshot deltas and exclude first
   observations.
4. All source access uses documented, free APIs and obeys rate limits, backoff,
   caching, and identification requirements.
5. Batch computation remains outside FastAPI, and the frontend remains behind
   the frozen API contract.
6. Time handling is UTC and aggregation is by ISO week.
7. Forecasts include backtested skill and render unsuccessful models as
   `no skill`.
8. Genres that fail a documented cross-source coverage gate render as
   `insufficient_evidence`, never as misleading zero activity.
9. `ruff`, strict `mypy`, and `pytest` are green.
10. The weekly automated pipeline still runs end-to-end without manual steps.
