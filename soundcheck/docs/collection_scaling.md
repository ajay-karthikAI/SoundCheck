# Collection Scaling and Resume Safety

Expansion Phase D widens Last.fm and MusicBrainz collection to the
source-specific spelling variants declared by every taxonomy-v2 `enabled` and
`candidate` genre. Rejected genres and the explicit `other` and `unresolved`
states never drive collection. This widens evidence gathering only: candidate
genres are not thereby enabled in metrics, forecasts, APIs, or the frontend.

## Fixed Source Limits

The existing official clients remain the only network path:

- Last.fm request starts are evenly spaced at a strict maximum of 4 per
  second;
- MusicBrainz request starts are evenly spaced at a strict maximum of 1 per
  second;
- both clients retain exponential backoff and SHA-256 disk caches;
- MusicBrainz retains the descriptive `Soundcheck/0.1 ( contact-email )`
  User-Agent;
- MusicBrainz pages are fetched sequentially and are never parallelized;
- cache hits do not acquire a network request slot because they make no
  request.

`config/collection_scaling.yml` repeats the rates as validated constants.
Configuration loading fails if either invariant is changed.

## Taxonomy-driven Tags

`GenreTaxonomy.collection_tags_v2(source)` collects the Last.fm or MusicBrainz
spelling variants for all enabled and candidate definitions. Tags are
deduplicated globally, ignoring case, and ordered deterministically.

The `production_compatibility` collector lists remain in the taxonomy only as
historical migration receipts. Current collectors no longer read those frozen
lists. Metrics, resolution, forecasts, and product surfaces remain on their
existing compatibility boundary until later validation phases.

## Last.fm Run Protocol

A resumable Last.fm run has three phases.

### 1. Tag discovery

Each deterministic tag shard fetches:

- `tag.getInfo`;
- `tag.getTopArtists`, capped at 100; and
- `tag.getTopAlbums`, capped at 50.

The parsed tag snapshot and artist references are stored as one immutable
DuckDB checkpoint. A completed tag is not requested again when the run resumes.

### 2. Global artist collection

Artist references from **all** completed tag shards are merged before any
`artist.getInfo` shard begins. Identity prefers MBID. A name-only reference is
promoted to an MBID only when that normalized name has one uniquely observed
MBID. Each global artist request retains the union of its source genres.

The resulting artist universe is deterministically sharded by request key.
Therefore an artist appearing under ten genres still produces one
`artist.getInfo` request for the run, not ten requests or one request per
shard. Not-found responses are checkpointed explicitly so they also do not
repeat on resume.

### 3. Atomic finalization

Every tag and artist result uses the run's original UTC `snapshot_at`, loaded
from immutable metadata when resuming. Finalization verifies that all expected
checkpoints exist, then appends tag and artist snapshots and writes the
run-complete marker in one DuckDB transaction.

If finalization is retried, the existing marker prevents a second append. Raw
Last.fm rows are never updated. Cumulative listeners and playcounts remain
lifetime snapshots; weekly listening change is still calculated only from
consecutive snapshots, first observations remain excluded, and missing first
deltas are never zero-filled.

## MusicBrainz Run Protocol

Incremental collection retains the inclusive trailing 14-day
`first-release-date` window. The as-of date is pinned for a GitHub Actions run
so reruns use the identical window.

Tags are assigned to deterministic external shards, then divided into bounded
query groups of at most 20 tags to avoid oversized Lucene queries. For each
query, pages use `limit=100` and increasing offsets. Every parsed page is an
immutable DuckDB checkpoint.

On interruption, pagination restarts at the first missing offset. Completed
pages are loaded from checkpoints and make no API request. Release groups are
deduplicated by MBID within the shard, then written through the existing
insert-on-first-sight table. A crash after insertion but before the shard
marker is safe: retrying the shard reaches `ON CONFLICT DO NOTHING`, so stable
MusicBrainz records are not duplicated or overwritten.

## Checkpoint Model

`stg_.collection_checkpoints` is the only resume store. Its key is:

```text
(source, run_key, phase, unit_key)
```

Rows are insert-only. Run metadata pins:

- taxonomy version;
- shard count;
- original snapshot time; and
- a fingerprint of tags, source, window, and shard count.

A resume with a changed taxonomy, date window, or shard count is rejected
instead of silently mixing plans. Checkpoints contain public parsed evidence,
never API credentials.

## Dry-run Planner

Run:

```bash
make plan-collection
```

The planner makes no network calls. It reports:

- taxonomy-v2 source tags;
- three Last.fm tag requests per tag;
- artists deduplicated from the latest existing tag snapshots;
- a conservative artist allowance for tags not yet observed;
- expected MusicBrainz pages;
- estimated uncached requests and runtime at the fixed source rates;
- explicit cache-hit assumptions; and
- the external shard count required to keep each shard within the configured
  safe window.

The formulas are:

```text
expected Last.fm artists
  = observed globally deduplicated artists
  + unobserved tags * expected artists per unobserved tag

Last.fm requests
  = 3 * tag count + expected Last.fm artists

MusicBrainz query groups
  = ceil(tag count / max tags per query)

expected MusicBrainz pages
  = max(
      query groups * expected pages per query,
      ceil(recent observed releases / page size)
    )

uncached requests
  = ceil(requests * (1 - cache-hit assumption))

runtime seconds
  = uncached requests / fixed requests per second

external shards
  = min(max shards, ceil(runtime / safe window))
```

The default cache-hit assumption is zero for both sources. This is
conservative: cache hits can shorten a run but are never required for the plan
to fit.

## GitHub Actions Behavior

The workflow computes the dry-run plan before collection.

- When a source's total runtime fits the safe window, the normal single-run
  target is used.
- Only when runtime exceeds the window does the workflow execute explicit
  deterministic shard phases.
- Last.fm always completes every tag shard before any artist shard.
- MusicBrainz shards and pages remain sequential under the shared 1-request-
  per-second client.

The DuckDB artifact is uploaded even on failure with the GitHub run attempt in
its name. A rerun first restores the latest artifact from its own prior
attempt, then resumes the same `COLLECTION_RUN_KEY`. The collection as-of date
is derived from the original GitHub run creation time, so the MusicBrainz
window does not drift between attempts.

## Operator Targets

```bash
# Read-only request and runtime plan
make plan-collection

# Single-run resumable collectors
make ingest-lastfm
make ingest-musicbrainz

# Explicit Last.fm shard phases
make ingest-lastfm-shard \
  RUN_KEY=example PHASE=tags SHARD_COUNT=3 SHARD_INDEX=0
make ingest-lastfm-shard \
  RUN_KEY=example PHASE=artists SHARD_COUNT=3 SHARD_INDEX=0
make finalize-lastfm RUN_KEY=example SHARD_COUNT=3

# Explicit MusicBrainz shard and finalization
make ingest-musicbrainz-shard \
  RUN_KEY=example SHARD_COUNT=2 SHARD_INDEX=0 AS_OF=2026-07-27
make finalize-musicbrainz \
  RUN_KEY=example SHARD_COUNT=2 AS_OF=2026-07-27
```

Changing `SHARD_COUNT` while resuming the same run key is intentionally
rejected. Start a new run key only when a genuinely new snapshot or date
window is intended.

## Limits

- Estimates for unobserved Last.fm tags are planning assumptions, not evidence
  or product metrics.
- MusicBrainz pages are estimated because result counts are known only after
  the first response for each query.
- Deterministic external shards bound resumable work units; they do not make
  strict-rate APIs complete faster.
- Cached Last.fm responses expire after six hours and MusicBrainz responses
  after 24 hours. Checkpoints, rather than caches, provide run-level resume
  guarantees.
