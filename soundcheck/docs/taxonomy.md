# Taxonomy v2

## Purpose and Phase Boundary

Soundcheck taxonomy v2 is the versioned identity layer for a genre-neutral
product with an indie-focused default view. It describes how genres relate,
which source spellings can identify them, and whether a definition is ready
for use. It does not claim that every modeled genre has adequate Bluesky,
Last.fm, and MusicBrainz coverage.

Expansion Phase B introduced taxonomy configuration and validation. Expansion
Phase D now lets enabled and candidate source spellings drive evidence
collection under the fixed API limits and resumable protocol documented in
[collection scaling](collection_scaling.md). Production API payloads continue
to use the frozen compatibility views in `config/genre_canonical.yml`.
Phase F writes coverage-gated v2 metrics beside the current marts, as
documented in [taxonomy-v2 metrics](metrics_v2.md), but does not switch
forecasts or API responses. Candidate genres cannot enter a production
surface merely because collection now observes them.

## Source of Truth

`config/genre_canonical.yml` is the only genre taxonomy source of truth. The
shared loader in `soundcheck/taxonomy.py` validates it with Pydantic v2 before
collectors, resolution, metrics, or API startup may use it. The previous
standalone collector tag file has been removed.

The root document contains:

- one semantic `taxonomy_version`;
- stable IDs for the default, `other`, and `unresolved` definitions;
- broad macro-family definitions;
- genre definitions;
- a temporary `production_compatibility` profile.

The compatibility profile preserves the pre-v2 collector tags as historical
receipts, plus the canonical metric labels and resolver overrides. It is an
explicit migration boundary, not a second taxonomy. Current collectors use
the v2 source spellings; derived production layers retain compatibility views
until a later phase validates coverage and output side by side.

## Genre Definition

Every genre has:

| Field | Contract |
| --- | --- |
| `genre_id` | Stable snake-case identity. It is the durable join key and must never be reused for another meaning. |
| `display_name` | Human-readable canonical label. A spelling change does not create a new identity. |
| `slug` | Unique, lowercase URL-safe label. Slug migrations must preserve old routes when API adoption begins. |
| `macro_family_id` | Required reference to one broad peer family. |
| `parent_genre_id` | Optional reference to another genre in the same macro family. |
| `aliases` | General exact-match spellings and established alternative names. |
| `multilingual_aliases` | Explicit aliases keyed by supported locale. Empty when no defensible alias is maintained. |
| `lastfm_spelling_variants` | Spellings observed or queried through the documented Last.fm interface. |
| `musicbrainz_spelling_variants` | Spellings observed or queried through the documented MusicBrainz interface. |
| `status` | One of `enabled`, `candidate`, or `rejected`. |
| `taxonomy_version` | Must equal the root taxonomy version. |

Source spelling fields express identity, not source coverage. Declaring a
Last.fm or MusicBrainz spelling does not mean the source contains enough data
for a product estimate.

## Macro Families

Macro families are stable peer-group containers, not claims that their
children have identical audiences or histories. Version 2 includes:

- African;
- Asian Regional;
- Caribbean;
- Classical;
- Electronic;
- Experimental and Ambient;
- Folk and Country;
- Hip-Hop;
- Jazz;
- Latin;
- Metal;
- Pop;
- Punk;
- R&B and Soul;
- Rock; and
- Unclassified.

Parents must remain inside their child's macro family. The loader rejects
unknown families, unknown parents, self-references, and cycles of any length.

## Status Semantics

### `enabled`

The definition is accepted by the taxonomy. Enabled source spellings can drive
collection, but only genres explicitly listed in the compatibility profile can
affect the current derived pipeline. `enabled` does not by itself mean a
genre-week has enough evidence to publish.

### `candidate`

The definition is plausible and useful for coverage measurement, alias
evaluation, and future migration work. Candidate genres do not enter the
current production canonical view.

### `rejected`

The label is retained so the system can explicitly refuse it. Labels such as
`world music`, `urban`, and `miscellaneous` are too broad or ambiguous to
serve as decision-ready canonical genres. Exact alias lookup does not resolve
to rejected definitions.

Taxonomy status and product evidence status are separate. A taxonomy-enabled
genre with weak cross-source evidence is `insufficient_evidence`, never zero
activity. The batch-computed eligibility states and thresholds are defined in
[data coverage](data_coverage.md); they do not automatically change taxonomy
status or production enablement.

## `other` and `unresolved`

These states are intentionally distinct:

- `unresolved` means the available label is unknown, ambiguous, rejected, or
  otherwise cannot be assigned safely. Exact alias lookup returns
  `unresolved` when there is not exactly one valid match.
- `other` is an explicit residual canonical category used only when the
  product has enough information to say the item is outside the maintained
  genre set.

An alias such as `garage` can legitimately exist in different macro families.
Without family context, that match remains `unresolved`; family context may
disambiguate it. The loader never selects a candidate merely because it is
the closest string.

The v1 embedding resolver retains its pre-v2 behavior through the
compatibility profile. The parallel taxonomy-v2 resolver now writes
below-floor results to `unresolved` without changing v1 results or production
surfaces. Its precedence, weighting, evaluation, and activation gates are
documented in [genre resolution v2](resolution_v2.md).

## Alias Normalization

Aliases are normalized deterministically by:

1. trimming whitespace;
2. applying Unicode compatibility decomposition and case folding;
3. removing combining marks so supported accented and unaccented forms match;
4. expanding `&` to `and`;
5. replacing punctuation and repeated whitespace with single spaces.

Normalization does not transliterate between writing systems. Japanese,
Korean, Chinese, and other non-Latin aliases are declared explicitly only
where supportable.

Within one macro family, a normalized alias can belong to only one genre.
Cross-family duplicates are allowed because context may disambiguate them.
Without that context, multiple matches resolve to `unresolved`.

## Determinism and Validation

The loader:

- sorts macro families by stable macro-family ID;
- sorts genres by stable genre ID;
- orders and deduplicates equivalent aliases deterministically;
- rejects duplicate genre IDs and slugs;
- rejects duplicate macro-family IDs and slugs;
- validates every parent and macro-family reference;
- rejects hierarchy cycles;
- rejects normalized alias collisions within a macro family;
- requires semantic version `2.x.y` at both root and genre level;
- validates every compatibility ID, collector tag, and override target.

Consumers must call `load_taxonomy`; they must not parse the YAML independently
or construct their own alias indexes.

## Versioning Policy

Taxonomy versions use semantic versioning within major version 2:

- **Patch** (`2.0.x`): correct metadata or add a non-conflicting spelling
  without changing canonical membership or hierarchy meaning.
- **Minor** (`2.x.0`): add candidates, enable an already evaluated definition,
  or introduce a backward-compatible relationship.
- **Major**: make an identity or hierarchy change that prevents direct
  comparison with version 2.

Stable IDs are never recycled. Merging or splitting a genre requires new IDs,
an explicit migration map, and parallel derived artifacts. Raw source tables
remain append-only. Existing `stg_`, `mart_`, and `fcst_` history is not
rewritten in place.

Before a candidate can become product-enabled, a later phase must publish:

- cross-source coverage and missingness;
- entity- and genre-resolution accuracy for the relevant family and language;
- sufficient valid Last.fm snapshot history;
- the effect on collection runtime under fixed source rate limits;
- side-by-side metric and forecast validation under the new taxonomy version.
