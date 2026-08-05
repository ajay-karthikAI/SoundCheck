# Taxonomy-v2 Data Coverage

Soundcheck measures whether a genre can support an evidence-backed product
claim before that genre is enabled. Coverage is batch-computed from the
existing DuckDB artifact. Expansion Phase C introduced this audit without
widening collection; Phase D subsequently widened evidence collection under
the separately documented [collection scaling](collection_scaling.md)
protocol. Coverage still does not enable an API, forecast, or frontend
surface. A `ready` row is now the mandatory input gate for the parallel
Phase-F metrics documented in [taxonomy-v2 metrics](metrics_v2.md); every
other state produces explicit null estimates.

The output is `mart_.genre_coverage_v2`, keyed by taxonomy version, ISO-week
Monday, and stable genre ID. Every taxonomy-v2 definition is present in the
weekly grid, including candidates and rejected genres. This makes failures
visible rather than silently dropping proposed genres.

## Evidence Mapping

Coverage uses exact normalized aliases declared in
`config/genre_canonical.yml`. Last.fm tags and artist source genres map through
Last.fm spelling variants; MusicBrainz genres and tags map through MusicBrainz
variants. Canonical labels and supported aliases are also eligible exact
labels. A label owned by more than one genre across macro families is ignored
when no family context disambiguates it. Embedding similarity is deliberately
not used for this gate.

Artist identities prefer MusicBrainz IDs. A normalized name becomes a fallback
identity only when no MBID is present; a name is promoted to an MBID only when
the observed evidence maps it uniquely. Coverage therefore follows the same
MBID-first principle as the join layer without claiming that name equality is
ground truth.

## Weekly Measures

All weeks are ISO weeks in UTC, represented by their Monday.

### Last.fm tag availability

`lastfm_tag_available` is `true` when a declared genre tag was observed that
week. No observation is `null`, not `false`.

### Unique Last.fm artists

`unique_lastfm_artists` is the count of distinct MBID-first artist identities
assigned by declared tags or source genres in the latest snapshot for that
artist and week:

```text
A(g,w) = |{artist identities observed for genre g in week w}|
```

When the set is empty because evidence is absent, the value is `null`.

### Artists with consecutive valid snapshots

`artists_with_consecutive_valid_snapshots` counts artists whose current and
previous latest weekly snapshots are exactly one ISO week apart and whose
cumulative listeners and playcount do not decrease:

```text
V(a,w) = 1 when
  snapshot(a,w-1) and snapshot(a,w) both exist,
  listeners(a,w) >= listeners(a,w-1), and
  playcount(a,w) >= playcount(a,w-1)

C(g,w) = sum_a V(a,w)
```

The first observation is excluded. It is never zero-filled and never treated
as listening activity. This measure checks whether a listening delta can be
formed; it does not use the cumulative totals as a weekly signal.

`lastfm_history_weeks` is the cumulative number of ISO weeks through the
reported week with a mapped Last.fm tag or artist observation. It identifies a
collector that is still accumulating the minimum history.

### MusicBrainz release supply

`musicbrainz_release_group_count` is the number of distinct release-group
MBIDs with a parseable full `first_release_date` inside the genre-week:

```text
R(g,w) = |{release-group MBIDs first released in genre g during week w}|
```

No matched release evidence is `null`. Coverage does not interpret missing
MusicBrainz evidence as zero supply.

### Resolved Bluesky conversation

`resolved_bluesky_post_count` is the count of distinct Bluesky post URIs whose
preferred staged artist link belongs to the genre. Preferred links use MBID
joins before name joins, then score and resolution time.

The measurable per-genre resolution denominator is:

```text
N(g,w) = resolved posts attributable to g
       + ambiguous attempts whose leading candidate is attributable to g

resolution_rate(g,w) = resolved_posts(g,w) / N(g,w)
```

An unresolved attempt with no genre-attributable candidate cannot honestly be
assigned to a genre and is excluded from the per-genre denominator. It remains
part of the separate global resolution evaluation. Consequently this rate is a
conditional genre-attributable rate, not the whole-corpus resolution rate.
When `N(g,w)` is absent, both the denominator and rate are `null`.

### Cross-source overlap

For every genre-week, let `L`, `M`, and `B` be the MBID-first artist sets
observed in Last.fm, MusicBrainz release credits, and resolved Bluesky posts.
Overlap is computed only when at least two source sets are present:

```text
U = L union M union B
O = {artist in U observed by at least two present sources}

cross_source_overlap_artist_count = |O|
cross_source_overlap = |O| / |U|
```

Unlike missing activity, a measured overlap of zero is meaningful and remains
`0`. If fewer than two sources contribute artist sets, both overlap fields are
`null`.

### Freshness and axis missingness

`latest_source_timestamp` is the maximum relevant `fetched_at`,
`ingested_at`, or `resolved_at` for the genre-week. `stale` is true when that
timestamp is absent or older than `max_source_age_days` at batch computation
time.

The three missingness flags are direct evidence statements:

- `listening_missing`: no artist has a consecutive valid Last.fm snapshot;
- `conversation_missing`: no resolved Bluesky post is attributable;
- `supply_missing`: no MusicBrainz release group is attributable.

The corresponding count stays `null`; a missing flag never causes a zero to be
written.

## Eligibility Thresholds

`config/coverage.yml` is the sole threshold configuration:

| Threshold | Default | Rationale |
| --- | ---: | --- |
| Lookback | 52 weeks | One bounded annual audit window without claiming seasonality |
| Last.fm tag required | yes | Requires an explicit collector-supported genre label |
| Unique Last.fm artists | 25 | Avoids treating one or two acts as genre coverage |
| Consecutive valid artists | 10 | Requires multiple usable delta series |
| Listening history | 2 weeks | Absolute minimum needed to form a weekly delta |
| MusicBrainz release groups | 1 | Requires observed release-supply evidence |
| Resolved Bluesky posts | 5 | Avoids a conversation claim from isolated posts |
| Resolution attempts | 5 | Prevents a perfect rate from one easy example |
| Resolution rate | 0.85 | Requires a high conditional success rate plus a minimum denominator |
| Overlapping artists | 2 | Requires more than a single cross-source bridge |
| Overlap rate | 0.10 | Requires at least a modest shared evidence base |
| Maximum source age | 14 days | Flags a missed weekly collection cycle |

These are conservative enablement gates, not statistical confidence claims.
They can be tightened through configuration after observed coverage is
reviewed. Weakening them requires an evidence-backed product decision.

## Eligibility States

States are assigned in deterministic priority order:

1. `unsupported`: rejected/special taxonomy category, no evidence, or stale
   evidence;
2. `collecting_history`: Last.fm collection exists but has not accumulated two
   weeks needed for a valid delta;
3. `insufficient_listening`: tag, artist breadth, or valid delta coverage
   misses its gate;
4. `insufficient_conversation`: resolved-post coverage misses its gate;
5. `insufficient_supply`: release-group coverage misses its gate;
6. `insufficient_resolution`: attempts, conditional resolution rate, or
   cross-source overlap misses its gate;
7. `ready`: every configured gate passes.

Priority identifies the first blocking prerequisite. The report still exposes
all axis measures and missingness flags, so later failures are not concealed.
`ready` means eligible for a parallel, uncertainty-bearing v2 metric. It does
not automatically enable a collector, production API, forecast, or frontend
surface.

## Running and Reporting

Compute from the current DuckDB artifact:

```bash
make coverage
```

Print the latest week's readable genre and macro-family tables:

```bash
make report-coverage
```

Emit JSON Lines for automation:

```bash
uv run python scripts/report_coverage.py --format jsonl
```

Use `--week YYYY-MM-DD` for one ISO-week Monday or `--all-weeks` for the full
persisted audit. Proposed genres that fail remain in both formats.

## Limits

- Exact aliases protect precision but can undercount untagged or novel
  spellings.
- MusicBrainz release-group rows are insert-on-first-sight and may reflect
  community completeness lag.
- The per-genre Bluesky resolution rate cannot attribute completely
  unrecognized posts; the separate labeled resolution evaluation remains the
  authority for whole-corpus precision and recall.
- Source overlap measures shared identifiable artists, not demographic
  representativeness.
- Historical genre-week rows eventually become stale relative to a current
  computation. Reporting defaults to the latest computed week; historical
  measures remain useful as receipts, not current eligibility claims.
