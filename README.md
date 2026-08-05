# Soundcheck

Soundcheck is a live, genre-neutral music trend-intelligence product with an
indie-focused default view. It serves music-platform data, editorial,
creator-success, and ecosystem-health teams by closing a three-way information
gap: music conversation shows what people discuss publicly on Bluesky,
listening change shows the movement between consecutive Last.fm snapshots, and
release supply shows which release groups first appeared in MusicBrainz.
Looking at any axis alone confuses social attention, changing consumption, and
available creation with generic popularity. Soundcheck compares all three,
preserves the receipts behind every score, and declines to make a claim when
the evidence is not ready.

Genre-neutral is the product direction, not a claim of universal source
coverage. Indie remains the default discovery lens while broader coverage is
measured. A genre without adequate evidence across the three sources is marked
`insufficient_evidence`, never displayed as zero activity. The scope and its
release gates are defined in
[product scope v2](soundcheck/docs/product_scope_v2.md).
The pre-enablement evidence audit is documented in
[data coverage](soundcheck/docs/data_coverage.md).
The measured migration and rollback gates are documented in
[taxonomy-v2 cutover](soundcheck/docs/taxonomy_v2_cutover.md).

## What the current evidence supports

These are the three findings the running application can support today. The
second and third are deliberately negative findings: cold-start uncertainty is
part of the result, not an empty state to disguise.

1. **Indie rock conversation spiked.** In ISO week `2026-07-20`, indie rock's
   within-week conversation index was **+3.97**, with a 90% interval of
   **[+3.97, +3.97]**, and the trend layer marked it as a spike. The collapsed
   interval reflects the current cell's limited resampling variation; it
   should not be read as perfect certainty.
2. **The discovery gap is not estimable yet.** In that week, **0 of 63**
   canonical genres had a valid listening observation, so indie rock's
   listening index, discovery gap, opportunity score, and their intervals are
   all absent—not zero. A second Last.fm snapshot in a later ISO week is
   required because first observations are intentionally excluded.
3. **No forecast has passed the validation gate.** The live artifact contains
   **3** metric weeks, below the **8**-week minimum, and therefore publishes
   **0** forecast rows. There is no honest out-of-sample MASE or prediction
   interval to quote yet. This is a failed readiness check, not a failed model,
   and Soundcheck does not substitute an in-sample result.

### Live verification ledger

Verified against the production API on `2026-07-28`. The hosted site exists at
[soundcheck-indie.ajayk19989.chatgpt.site](https://soundcheck-indie.ajayk19989.chatgpt.site)
and currently requires owner authentication.

| Claim | Live source | Returned evidence |
|---|---|---|
| Data state | [`/api/health`](https://soundcheck-api.vercel.app/api/health) | read-only; latest metric week `2026-07-20`; 189 metric rows; 0 forecast rows; no complete week or pipeline manifest |
| Indie rock spike | [`/api/genres/indie%20rock/timeseries?weeks=3`](https://soundcheck-api.vercel.app/api/genres/indie%20rock/timeseries?weeks=3) | conversation `3.969631184335433`; lower and upper `3.969631184335433`; `spike: true` |
| Discovery-gap readiness | [`/api/ecosystem?weeks=3`](https://soundcheck-api.vercel.app/api/ecosystem?weeks=3) | 63 canonical genres; 0 listening-observed and 0 opportunity-observed genres |
| Forecast readiness | [`/api/forecast/next-up?limit=20`](https://soundcheck-api.vercel.app/api/forecast/next-up?limit=20) | empty array |
| Taxonomy-v2 production state | [`/api/v2/taxonomy`](https://soundcheck-api.vercel.app/api/v2/taxonomy) | HTTP 404; v2 has not been cut over |

## Method

Each weekly batch ingests public Bluesky music conversation, append-only
Last.fm cumulative snapshots, and MusicBrainz release groups; resolves posts
and source tags to canonical artists and genres; derives within-week,
shrinkage-aware indices; backtests candidate forecasts against persistence; and
publishes a read-only evidence API. Last.fm contributes listening change only
as deltas between consecutive snapshots—never lifetime totals as weekly
activity. MusicBrainz contributes release supply rather than an estimate of
catalog popularity. The statistical definitions and uncertainty rules are in
[metrics](soundcheck/docs/metrics.md), forecast validation is in
[forecasting](soundcheck/docs/forecasting.md), source handling is in
[data provenance](soundcheck/docs/data_provenance.md), and the implied creator
experiment is pre-specified in
[experiment design](soundcheck/docs/experiment_design.md).

## Resolution quality

The checked-in evaluation fixture contains **60** examples, but **0** currently
have human labels. The evaluation harness therefore reports precision
**not available** and recall **not available**, with thresholds disabled. That
is the only defensible result; Soundcheck does not turn unlabeled examples into
a precision claim. Labeling the fixed fixture is required before entity
resolution can be described as validated.

Reproduce the status:

```bash
uv run python -m soundcheck.scripts.eval_resolution
```

## Review it in 90 seconds

Hosted application:
[soundcheck-indie.ajayk19989.chatgpt.site](https://soundcheck-indie.ajayk19989.chatgpt.site)
(owner authentication required). For a local review, start the API with
`make api`, then follow [soundcheck/web/README.md](soundcheck/web/README.md).

- **0:00–0:20 — `/next-up`:** inspect the validation gate and the promise that
  unskilled forecasts remain visible rather than being hidden.
- **0:20–0:40 — `/gap`:** see why listened-not-discussed and
  hype-outruns-listening are treated as different product opportunities.
- **0:40–1:00 — `/ecosystem`:** read discovery as platform health through
  diversity, concentration, and scene churn.
- **1:00–1:15 — `/`:** inspect the opportunity board, using the gold
  `SUPPLY = 0` and `DEMAND = 0` guides to locate each scene relative to the
  decision thresholds.
- **1:15–1:30 — `/methods`:** verify the formulas, backtest protocol, and
  current insufficient-history result.

### Read the opportunity board

The opportunity board places release pressure on the horizontal axis and
audience demand on the vertical axis. The heavier gold guides mark exactly
`x = 0` and `y = 0`, making the four decision regions explicit:
demand with room for new releases, demand with a crowded supply field, quiet
space with room, and quiet space that is already crowded.

Some genres share the same underlying supply value. The chart separates those
ties horizontally with a deterministic beeswarm so their evidence remains
inspectable instead of being drawn on top of itself. This spacing is
display-only: the tooltip always reports the exact release-pressure value.
Point color continues to show the conversation-versus-listening mismatch, and
point size continues to represent evidence volume.

### Populate every tab immediately with synthetic data

For product evaluation before the observed dataset clears its cold-start
gates, generate the isolated demo artifact:

```bash
make demo-data
make demo-api
```

Then run the frontend normally. The generator writes only
`data/soundcheck-demo.duckdb`, marks its pipeline trigger as
`synthetic_demo`, and causes the frontend to display a persistent
“Synthetic demo data” banner. Stop the demo API and run `make api` to return
to the observed artifact.

## Provenance posture

Soundcheck uses official, documented, free interfaces only: public Bluesky
Jetstream and AppView, the free Last.fm API, and the public MusicBrainz API.
It collects no private Bluesky data or individual Last.fm listening histories,
and raw source identifiers remain attached to downstream evidence.

Presence in an official source does not by itself establish adequate genre
coverage. Cross-source eligibility must be measured and published before a
genre is treated as decision-ready; otherwise its status is
`insufficient_evidence`.

SoundCloud is rejected because application registration has a paid Artist Pro
prerequisite. Bandcamp is rejected because it has no official API and would
require scraping. Those gaps are accepted rather than worked around.

## Limitations

- Last.fm scrobblers are a self-selected population and are not a census of
  music listening.
- MusicBrainz is community-maintained; newly released or niche work can arrive
  late or remain incomplete.
- Bluesky's users and posting behavior are not demographically representative
  of the full listener market.
- Artist and genre resolution remain unvalidated until the human-labeled
  evaluation is complete.
- Weekly aggregation cannot establish that conversation caused later
  listening; the proposed causal design and its assumptions are documented,
  not asserted as a result.
- The present artifact is a cold start. Discovery-gap, opportunity, forecast,
  and creator-brief claims remain suppressed until their evidence gates pass.
- The genre-neutral scope does not make the current artifact representative of
  every genre. Mainstream, regional, and multilingual coverage must be
  measured separately before those genres are enabled.

## What's next

Collect the next Last.fm snapshot in a later ISO week, complete the fixed
resolution labels, and let the scheduled artifact accumulate enough
consecutive weeks for rolling-origin validation. In parallel, the expansion
must pass its family-specific resolution, cross-source coverage, missingness,
history, forecast, runtime, and freshness gates before enabling the v2
frontend. Once a forecast has a genuinely held-out outcome, add the first
verified win—or visible no-skill result—to this data story. Deployment and
rollback are described in
[deployment setup](soundcheck/scripts/deploy.md); a failed taxonomy comparison
keeps the currently deployed site version in place.
