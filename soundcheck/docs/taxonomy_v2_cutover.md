# Taxonomy v2 cutover

## Decision rule

Taxonomy v2 is a parallel, measured migration. It is not a rewrite of
taxonomy v1 and it is not enabled merely because its tables contain rows. The
cutover decision is generated from
`config/taxonomy_v2_cutover.yml` by:

```bash
make compare-taxonomies
```

The report is read-only. It compares the current DuckDB artifact with the
human-label evaluation fixtures and prints every family and global gate. A
release automation may require a passing decision with:

```bash
uv run python scripts/compare_taxonomy_versions.py --require-cutover
```

Missing evidence fails closed. It is never converted to zero activity, an
assumed resolution label, an estimated forecast skill, or a passing gate.

## Historical isolation

The migration preserves four independent histories:

- every `raw_` table remains append-only;
- taxonomy-v1 staging tables remain unchanged;
- taxonomy-v1 `mart_` and `fcst_` rows remain unchanged;
- taxonomy-v2 writes only to its versioned `stg_`, `mart_`, and `fcst_`
  tables.

Existing raw Last.fm tags and artists, MusicBrainz releases, and Bluesky
evidence are re-resolved under taxonomy `2.0.0`. Re-running v2 resolution is
incremental and idempotent. Last.fm listening continues to use deltas between
consecutive append-only snapshots; re-resolution cannot create an event from
a lifetime total or make a first observation eligible.

The version-isolation tests insert v1 sentinels, run v2 persistence twice, and
verify the v1 records remain intact. The comparison report itself opens
DuckDB in read-only mode.

## Cutover gates

Thresholds are configuration, not informal reviewer judgment.

| Scope | Gate | Required result |
| --- | --- | --- |
| Each enabled macro family | Resolution | At least 20 human-labeled examples, precision at least 0.90, recall at least 0.75, and MBID precision at least 0.98 |
| Each enabled macro family | Cross-source coverage | At least 3 enabled genres and 60% of enabled genres are `ready`; each ready genre has cross-source overlap of at least 0.10 |
| Each enabled macro family | History | At least 3 ready genres have 8 or more eligible ISO weeks |
| Each enabled macro family | Missingness | No more than 40% of enabled genres are missing; every ready estimate has its required interval |
| Each enabled macro family | Forecast validation | At least 4 publishable rows; every row has a point inside its interval, genre and family validation, empirical 80% interval coverage of at least 0.60, and a naive receipt |
| Global | Runtime | A successful weekly manifest completes in at most 300 minutes |
| Global | Recovery plan | At most 16 deterministic shards per source and at most 1,800 estimated seconds per shard |
| Global | Freshness | Latest source evidence is no more than 14 days old |

The interval-coverage cut is deliberately below the nominal 0.80 because the
current backtest history is short; the actual coverage remains published.
This tolerance permits noisy but measurable calibration. It does not waive
the eight-week minimum, the naive comparison, or the `no_skill` outcome.

`no_skill` is a valid and visible forecast result only when the naive forecast,
its interval, and the relevant validation ledger are present. It is not a
substitute for `insufficient_history`.

## Family activation

Activation is family-specific. A family that misses any family gate remains
`candidate` or disabled. Its evidence remains available for comparison and
labeling, but it is excluded from production rankings. `other` and
`unresolved` remain distinct and neither can become eligible by inference.

The frontend cutover is all-or-nothing for the currently enabled family set.
The report emits `enable_v2_frontend` only when every enabled-family gate and
every global gate passes. Otherwise it emits `hold_v1_frontend`.

## What the comparison measures

`scripts/compare_taxonomy_versions.py` reports:

- latest genre and macro-family coverage;
- source-tag mappings that changed between the flat v1 compatibility mapping
  and hierarchical v2 multi-membership;
- the v1 `other` rate and the explicit v2 `unresolved` rate;
- human-labeled precision and recall overall and by family;
- opportunity rank and value changes on the latest comparable week;
- discovery-gap rank and value changes on the latest comparable week;
- selected forecast status, model, MASE, and family MASE changes;
- missing listening and opportunity estimates that changed state; and
- collection, runtime, and freshness evidence.

An empty opportunity or discovery-gap comparison means no common eligible
estimate exists. It does not mean the versions agree.

## Current measured decision

The local observed artifact was evaluated on 2026-07-28. The report found:

- latest coverage week: 2026-07-20;
- 129 genre coverage rows across the taxonomy;
- 0 human-labeled v1 examples and 0 human-labeled v2 examples;
- 0 ready enabled genres in every currently enabled family;
- 0 ready genres with the eight-week history minimum;
- 0 publishable family-validated forecast rows;
- 714 of 1,615 v2 source tags explicitly unresolved (44.2%);
- no successful weekly runtime manifest; and
- 46 failed cutover gates.

The resulting action is `hold_v1_frontend`. These are local migration
measurements, not production claims. They must be regenerated after each full
weekly run.

## Dual-run automation and recovery

During comparison, the scheduled weekly job keeps this dependency order:

```text
ingest
→ resolve v1, then resolve v2 and coverage
→ metrics v1, then metrics v2
→ forecast v1, then forecast v2
→ briefs
→ immutable DuckDB plus comparison-report artifact
→ API deploy
```

The ordering is one dependency chain even though each compute stage writes
both versions. Daily jobs stop after ingestion.

Collectors use date-pinned deterministic shards and resumable checkpoints.
The immutable workflow artifact retains both the DuckDB file and the JSON
comparison report for 90 days. A failed attempt first restores its own latest
checkpoint artifact; otherwise it restores the latest successful artifact.
The raw append-only keys, version-scoped replacement logic, and stable
MusicBrainz insert-on-first-sight keys make a rerun recoverable without
rewriting observations.

The workflow deploys a refreshed read-only API only after the data pipeline
and quality gates execute successfully. An explicit
`cutover_taxonomy_v2=true` dispatch fails before deployment if the comparison
decision is not passing. A passing report still requires a separate,
intentional Sites version deployment to change the frontend.

## Production verification

Before enabling a new Sites version, verify against the production API:

1. `/api/health` reports `ok`, `read_only`, a successful latest pipeline run,
   and a fresh complete week.
2. `/api/v2/coverage` returns explicit coverage states and null missing
   evidence.
3. `/api/v2/opportunities` returns uncertainty bands for every estimate.
4. One eligible genre evidence endpoint returns direct Bluesky, Last.fm, or
   MusicBrainz receipts.
5. `/api/v2/forecast/next-up` returns intervals, MASE, interval coverage, and
   visible `no_skill` rows where applicable.
6. The v1 OpenAPI paths and payload tests still pass.
7. The frontend footer's “data through” date agrees with API freshness.

If any check fails, do not deploy the v2 frontend.

## Cutover procedure

1. Run all Python and frontend quality gates.
2. Run a complete weekly dual pipeline from a restored immutable artifact.
3. Save the JSON comparison report with that same artifact.
4. Run the comparison again with `--require-cutover`.
5. Record the active and candidate Sites version IDs, the Vercel deployment
   ID, and the workflow artifact name.
6. Verify the production API checks above.
7. Deploy the already-saved v2 Sites version.
8. Re-run production checks through the frontend.

No deployment is authorized by a report that says `hold_v1_frontend`.

## Rollback

Rollback changes aliases and deploy pointers; it does not delete or mutate
data.

1. Redeploy the recorded previous Sites version.
2. Promote the recorded previous immutable Vercel API deployment.
3. If the API artifact itself is suspect, restore the recorded previous
   workflow DuckDB artifact and rebuild that immutable API bundle.
4. Keep taxonomy-v2 tables for investigation; continue writing v1 and v2 in
   parallel unless the failure is caused by v2 runtime pressure.
5. Re-run v1 health, evidence, uncertainty, no-skill, and freshness checks.
6. Record the failed gate and leave affected families candidate or disabled.

Because v1 data and saved site versions are retained, rollback never requires
editing raw evidence or reconstructing v1 historical results.
