# Genre Resolution v2

## Product Boundary

Taxonomy-v2 resolution turns source folksonomies into measured, versioned
artist memberships. It does not change the current production marts, forecasts,
API contract, or frontend. The existing `stg_.tag_genre_map` and all v1
results remain intact. Version 2 writes parallel tables and cannot enter
production until its human-labeled evaluation activates the relevant macro
family.

The resolver answers two related questions:

1. Which maintained genre definitions can a Last.fm or MusicBrainz tag
   identify?
2. Given all tag evidence for an artist, how should that artist's membership
   be distributed across genres and macro families?

The output is membership evidence, not a claim that an artist has one
essential genre.

## Inputs

The batch uses only existing official-API evidence in DuckDB:

- Last.fm artist tags and the collection genres through which the artist was
  observed;
- MusicBrainz genres attached to release groups;
- MusicBrainz counted tags attached to release groups; and
- artist MBIDs and names retained with those source records.

Last.fm lifetime listener and playcount totals are not used for resolution.
This phase neither changes nor relaxes the append-only snapshot and
delta-only listening rule.

`config/genre_canonical.yml` supplies the stable taxonomy IDs, hierarchy,
aliases, multilingual aliases, source spelling variants, special states, and
manual overrides. `config/resolution_v2.yml` supplies the semantic-matching,
evidence-weight, and activation thresholds. The two files must declare the
same `taxonomy_version`.

## Tag Resolution Ladder

For each normalized source tag, precedence is deterministic:

1. **Manual override.** An explicit override maps with confidence `1.0` and
   weight `1.0`.
2. **Exact alias.** Canonical names, slugs, general aliases, Last.fm variants,
   and MusicBrainz variants map with confidence `1.0`.
3. **Exact multilingual alias.** Explicit locale-keyed aliases map with
   confidence `1.0` while retaining their declared language.
4. **Embedding.** Otherwise, `all-MiniLM-L6-v2` cosine similarity is compared
   with every non-rejected canonical genre except `other` and `unresolved`.

An alias owned by more than one macro family is `ambiguous_exact` unless a
manual override resolves it. An alias retained on a rejected taxonomy
definition is `rejected_alias`. Both produce an explicit `unresolved`
mapping. No string-distance fallback overrides these decisions.

### Embedding membership

Let \(s_g\) be the cosine similarity between source tag \(t\) and canonical
genre \(g\). The configured floor is \(c=0.55\). If
\(\max_g s_g < c\), the result is `below_floor` and maps explicitly to
`genre_unresolved`.

Above the floor, up to three genres within `0.05` of the best similarity are
retained. Their tag-membership weights use a temperature-scaled softmax:

\[
w_{t,g} =
\frac{\exp((s_g-s_{\max})/\tau)}
{\sum_{h \in A_t}\exp((s_h-s_{\max})/\tau)}, \qquad \tau=0.10
\]

where \(A_t\) is the accepted set. The weights for one source tag sum to one.
Confidence remains the measured cosine similarity and is stored separately
from membership weight.

## `other` and `unresolved`

The two states are not interchangeable:

- `other` is emitted only when source evidence explicitly matches the
  maintained `other` definition.
- `unresolved` means the tag is unknown, ambiguous, rejected, or below the
  semantic floor.

The embedding candidate set excludes both special genres. A weak nearest
neighbor can therefore never be forced into `other` or a named genre.

## Artist Memberships

Artists are keyed by MBID whenever one is available. A normalized name key is
used only when the evidence cannot be connected to a unique MBID. This
`join_key_type` is retained for stratified evaluation.

An artist may have multiple subgenre and macro-family memberships. For source
evidence \(e\) and mapped genre \(g\), the unnormalized contribution is:

\[
a_{e,g} = q_{\operatorname{source}(e)} w_{e,g}
\]

with configured source weights:

| Evidence source | \(q\) |
| --- | ---: |
| MusicBrainz genre | 1.00 |
| MusicBrainz tag | 0.85 |
| Last.fm tag or collection genre | 0.75 |

For artist \(a\), contributions are summed and normalized:

\[
W_{a,g} =
\frac{\sum_{e \in a} a_{e,g}}
{\sum_h \sum_{e \in a} a_{e,h}}
\]

The artist's membership weights sum to one. Mapping confidence is aggregated
separately as the contribution-weighted mean. If an artist has any resolved
genre evidence, unresolved contributions do not dilute the valid
memberships. If every contribution is unresolved, the artist retains an
explicit unresolved membership rather than disappearing.

## Parallel Storage Contract

`stg_.tag_genre_map_v2` stores one or more rows per source tag:

- `source_system`, `source_tag`, and `normalized_source_tag`;
- `canonical_genre_id`, `macro_family_id`, and `parent_genre_id`;
- `membership_weight`, `method`, `confidence`, and `language`;
- `model_name`, `taxonomy_version`, and `resolved_at`.

`stg_.artist_genre_memberships_v2` stores:

- MBID-first artist identity and `artist_key_type`;
- canonical, macro-family, and parent membership;
- normalized membership weight and measured confidence;
- contributing source systems and source tags;
- an input fingerprint, taxonomy version, and resolution timestamp.

`stg_.canonical_genre_embeddings_v2` preserves the exact vector basis for
scene-map and audit work. `stg_.artist_genre_resolution_state_v2` stores the
last input fingerprint. `stg_.genre_family_activation_v2` stores measured
evaluation status. None of these tables replaces or mutates a v1 table.

## Incremental and Idempotent Behavior

Tag mappings use the key
`(taxonomy_version, source_system, normalized_source_tag,
canonical_genre_id)`. Previously mapped tags are not recomputed within the
same taxonomy version.

Canonical embeddings are inserted only when the taxonomy-version/model pair
does not already contain that genre ID. An unchanged rerun therefore does not
refresh audit timestamps or rewrite identical vectors.

For each artist, the resolver hashes the sorted source system, normalized tag,
and evidence timestamp. An unchanged fingerprint performs no membership
write. A changed artist replaces only that artist's rows for the same taxonomy
version in one transaction, then advances the state fingerprint. Re-running
the same inputs writes no duplicate mappings and changes no artists.

Raw Last.fm snapshots remain append-only. A new snapshot timestamp changes
the fingerprint and permits a new resolution pass without overwriting source
evidence.

## Evaluation and Activation

`tests/fixtures/resolution_v2_eval.jsonl` is a 480-row, deterministic,
stratified labeling set built from current v2 artist memberships, tag
mappings, and declared multilingual aliases. It spans macro family, language,
source, mapping method, MBID/name join key, and popularity tier.

The generator never creates a human label and preserves existing labels by
stable `example_id`. A positive human label must include the accepted
`label_genre_ids`; a negative label must contain none.

Precision and recall are computed over predicted and human-labeled genre-ID
sets:

\[
\operatorname{precision}=\frac{TP}{TP+FP}, \qquad
\operatorname{recall}=\frac{TP}{TP+FN}
\]

The report includes results by:

- macro family;
- language;
- Last.fm or MusicBrainz source;
- resolution method;
- `mbid`, `name`, or `unknown` join key; and
- popularity tier.

Activation thresholds are configurable in `config/resolution_v2.yml`.
Currently a family needs at least 20 labeled examples, precision of at least
`0.90`, recall of at least `0.75`, and MBID precision of at least `0.98`.
Overall measured precision has a `0.85` quality floor. A family with too few
labels, missing MBID evaluation, or a failed quality threshold remains
`candidate` with explicit reasons and `production_eligible=false`.
`macro_unclassified` is never activated: `other` and `unresolved` are audit
states, not a product comparison family.

No human labels were available when Phase E generated the fixture. Therefore
the measured report is `awaiting_labels`, and all 16 macro families correctly
remain candidates. This is a lack-of-evidence statement, not a precision
claim.

## Commands

Run only the offline v2 genre resolver:

```bash
make resolve-v2
```

Run v1 entity and genre resolution followed by the parallel v2 pass:

```bash
make resolve
```

Regenerate the stratified fixture without overwriting human labels, then
evaluate the labeled portion:

```bash
make generate-resolution-v2-eval
make eval-resolution-v2
```

The evaluation command persists family decisions to
`stg_.genre_family_activation_v2`. Use `--no-persist` for a read-only report.

## Limitations

- Folksonomy tags describe source communities and can be inconsistent even
  when resolved correctly.
- Embedding similarity is semantic evidence, not a human genre judgment.
- Multilingual evaluation remains sparse until humans label enough
  source-grounded examples per language and family.
- A name-key membership is weaker than an MBID-key membership and is reported
  separately.
- Multi-genre weights express the balance of available tag evidence, not a
  probability that an artist “is” a genre.
- Passing resolution thresholds does not bypass source-coverage, listening
  history, uncertainty, forecast-skill, or API migration gates.
