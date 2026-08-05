# Soundcheck Product Scope v2

## Product Decision

Soundcheck is a genre-neutral music trend-intelligence product with an
indie-focused default view. It serves music-platform data, editorial,
creator-success, and ecosystem-health teams.

Genre-neutral describes which music Soundcheck is designed to evaluate; it
does not claim that every genre is currently measurable. Indie remains the
default entry point while the product expands its taxonomy and validates
cross-source coverage. Expansion does not lower the evidence, uncertainty,
resolution, or forecasting standards applied to the existing product.

This document defines product scope only. It does not change the collectors,
metrics, API contract, forecasts, or frontend behavior.

## The Signals Are Not Generic Popularity

Soundcheck measures three distinct parts of a music ecosystem:

- **Music conversation** is the volume and engagement of qualifying public
  Bluesky posts. It describes public discussion on one social network, not
  total audience size, cultural importance, or market-wide popularity.
- **Listening change** is the week-over-week change in Last.fm artist
  listeners and playcounts derived from consecutive, append-only snapshots.
  Lifetime totals and first observations are not weekly activity.
- **Release supply** is the count of MusicBrainz release groups first released
  in a genre and ISO week. It measures documented release availability, not
  release quality, catalog size, or every release made worldwide.

The product value comes from comparing these signals—with their evidence,
missingness, and uncertainty—not from collapsing them into a generic
popularity chart.

## Target Users and Their Decisions

| Team | Decisions Soundcheck should inform |
| --- | --- |
| Music-platform data | Which genre movements warrant investigation, where demand and supply are diverging, and whether a forecast has enough backtested skill to support a decision. |
| Editorial | Which scenes, artists, and releases merit human review, and what source evidence explains a movement. Soundcheck informs editorial judgment; it does not automate it. |
| Creator success | Which adequately evidenced scenes may offer room for new work, what is driving the signal, and which crowded adjacent genres a creator may want to avoid imitating. |
| Ecosystem health | Whether attention is diversifying or concentrating, whether scenes are rotating, and whether an intervention could reduce diversity by sending too many creators toward the same signal. |

## Primary Product Questions

Every product surface must answer at least one of these questions:

1. Where are music conversation and listening change outrunning release
   supply?
2. Which genres may move next week, with what interval, and did the selected
   model beat a naive baseline in backtests?
3. Where does listening change exceed music conversation, or conversation
   exceed listening change?
4. Is the measured music ecosystem becoming more diverse, concentrated, or
   fast-rotating?
5. What could a creator make in response to an evidenced opening without
   simply copying an already crowded adjacent scene?
6. What raw posts, artist snapshots, and releases support each conclusion?

## Why Indie Remains the Default Lens

Indie is the default view, not an eligibility rule or a separate statistical
standard.

- Soundcheck began with an indie discovery question, so the existing product
  story, taxonomy, and accumulated evidence are strongest there.
- Opportunity and discovery-gap analysis are especially useful in fragmented
  scenes where attention can move before release supply catches up.
- Keeping a stable default preserves continuity while broader genre coverage
  is measured rather than assumed.
- An indie default provides a coherent starting view without implying that
  mainstream volume is the benchmark for every scene.

Broader genres must meet the same evidence, uncertainty, resolution, and
forecast-validation requirements. The default lens must never be used to
quietly apply weaker standards elsewhere.

## What Genre-Neutral Includes

The intended scope includes:

- mainstream, independent, regional, electronic, acoustic, experimental, and
  other music genres that can be represented by a versioned canonical
  taxonomy;
- multiple spellings, aliases, and parent-child genre relationships when they
  have been explicitly modeled and evaluated;
- international and multilingual genres when source coverage and resolution
  quality are measured for the relevant language and market context;
- comparisons across the full set of eligible genres and, in a later phase,
  comparisons within suitable peer families;
- explicit unresolved, other, cold-start, and insufficient-evidence states.

A genre is decision-ready only for the genre-weeks in which its cross-source
evidence and resolution quality clear published gates.

## What Genre-Neutral Excludes

The scope does not include:

- a claim of exhaustive coverage of all music or all listeners;
- private platform data, scraped data, paid APIs, or paid-account
  prerequisites;
- treating Bluesky discussion, Last.fm users, or MusicBrainz submissions as a
  representative census of the global music market;
- inferring causality from a correlation between conversation and listening;
- charting raw lifetime totals as weekly listening activity;
- forcing a weak genre match so that every source record appears classified;
- displaying an unsupported genre as zero activity;
- a track recommendation engine, an automated editorial desk, or a generic
  popularity leaderboard.

## Evidence Eligibility and Missingness

Every genre-week must carry an evidence status. A product score is eligible
only when the genre has adequate evidence across music conversation,
listening change, and release supply, and when its entity and genre resolution
meet published quality requirements.

Genres that do not meet those requirements are marked
`insufficient_evidence`. They are never displayed as zero activity. Missing
signals remain missing, first Last.fm observations remain excluded, and a
forecast without enough history remains a cold start. These states must not be
converted into neutral-looking scores.

Expansion Phase C now defines conservative coverage, resolution, freshness,
overlap, and history gates in `config/coverage.yml`; their formulas and
rationale are published in [data coverage](data_coverage.md). The detailed
batch states diagnose the first failed prerequisite. Until a later reviewed
cutover, none of those states enables a collector or production surface, and
every non-ready genre continues to satisfy the product-level
`insufficient_evidence` rule.

## Risks of Expanding into Mainstream Genres

### Volume can overwhelm comparison

High-volume mainstream genres could dominate global rankings and make smaller
scenes look inactive. Future statistical design must preserve within-week
standardization and evaluate peer-family comparisons without hiding absolute
coverage.

### Source populations are not market populations

Bluesky, Last.fm, and MusicBrainz have different demographic, geographic, and
genre skews. Mainstream visibility on one source may amplify those skews
rather than validate broad popularity.

### Taxonomy ambiguity grows

Popular artists often span several genres, and regional or multilingual genre
names may not map cleanly to an English-language taxonomy. Weak matches would
contaminate every downstream score, so unresolved records must remain
unresolved.

### Collection cost and runtime grow

Adding tags and artists increases collection time while the Last.fm
four-request-per-second and MusicBrainz one-request-per-second limits remain
absolute. Expansion may require resumable shards, caching, and narrower
eligibility—not relaxed limits.

### Historical comparability can break

Changing genre definitions can rewrite apparent trends. Taxonomy versions and
parallel derived artifacts are required before any production cutover; raw
source history remains append-only.

### Forecast cold starts multiply

New genres initially lack enough valid weekly deltas for backtesting.
Insufficient history must stay visible, and forecast skill from an indie
sample cannot be transferred to another genre family without validation.

### Product recommendations can change the ecosystem

Sending many creators toward the same opening can crowd the scene and destroy
the signal that prompted the recommendation. Diversity and concentration
guardrails remain part of the product decision, not a reporting afterthought.

## Success Criteria

The expansion succeeds when:

- target teams can use the same evidence-backed product questions across
  every enabled genre;
- each enabled genre clears published cross-source coverage and resolution
  gates;
- all derived claims retain raw evidence, uncertainty, and missing-data
  status;
- indie remains a coherent default view while broader genres use the same
  methodology;
- expanded collection remains self-updating and respects every source limit;
- forecasts are evaluated by genre context and retain `no skill` and
  cold-start outcomes;
- taxonomy versions preserve historical interpretability;
- no existing API, datastore, Last.fm delta, or automation invariant is
  weakened.

## Cut Criteria

An expansion unit—a genre, family, source mapping, or proposed surface—is cut
or held back when:

- it requires scraping, a paid API, private data, or a paid-account
  prerequisite;
- cross-source coverage or resolution quality does not clear the published
  gate;
- its history is too short to support the promised comparison or forecast;
- it cannot retain evidence links and honest uncertainty;
- it would represent missing evidence as zero activity;
- it cannot run within documented rate limits and the automated weekly
  pipeline;
- it produces only a generic popularity ranking rather than informing a
  defined product decision.

A model that fails to beat the naive baseline is not silently cut; it is
published as `no skill` when the forecast contract permits publication.

## Transition Boundary

Expansion Phase A changed the product definition and documentation only.
Expansion Phase B adds a versioned taxonomy while freezing the existing
collector, metric, forecast, API, and frontend views behind an explicit
compatibility profile. Candidate definitions do not become production
coverage until later phases measure and validate them explicitly. No current
coverage, finding, forecast, or live deployment claim follows merely from
adopting this scope or adding a candidate genre.
