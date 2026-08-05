# Soundcheck application assets

## Suno project summary

Soundcheck is a genre-neutral trend-intelligence product for music content
ecosystems, with indie as its default discovery lens. It connects music
conversation on Bluesky, week-over-week listening change from Last.fm
snapshots, and release supply from MusicBrainz to show where attention may be
outrunning available creation. These are distinct signals, not a generic
popularity score, and every claim retains its evidence and uncertainty. For
creators, Soundcheck asks what they can make that meets emerging demand without
copying an already crowded scene. For music-platform data, editorial,
creator-success, and ecosystem-health teams, it asks whether social discovery
becomes durable listening, where release supply is thin, and whether attention
is diversifying. Genres without adequate cross-source coverage are labeled
insufficient_evidence, never zero. Forecasts that cannot beat persistence
remain visible as no skill. The result is a product framework for guiding
creator strategy while protecting pluralism, transparency, and the long-term
health of the content ecosystem as it evolves responsibly.

_Word count: 150._

## What I would investigate in my first month at Suno

- **Opportunity → creator success:** Which adequately evidenced sounds have
  rising listening change and music conversation but limited release supply,
  and which guidance helps creators act without making the output feel
  imitative?
- **Discovery gap → social discovery:** Where do listening change, shares,
  remixes, follows, and external music conversation diverge—and which
  in-product discovery surfaces close that gap?
- **Forecasts → product allocation:** Can short-horizon demand forecasts beat a
  persistence baseline well enough to guide recommendation inventory, creator
  education, and editorial attention?
- **Ecosystem health → durable growth:** Are discovery and creation broadening
  across genres and creator cohorts, or is the platform concentrating attention
  in ways that reduce long-run novelty?
- **Evidence lineage → trustworthy decisions:** Which genres have adequate
  cross-source coverage, how reliably can songs, creators, prompts, remixes,
  and listening outcomes be joined, and where should the answer remain
  `insufficient_evidence`?

## 60-second demo script

### 0:00–0:12 — `/next-up`

“Soundcheck starts with the decision, not a dashboard: what is likely to move
next week? Each row carries a prediction interval, the selected model, its
held-out MASE, and the naive forecast. If no model wins, it says ‘no skill.’”

### 0:12–0:24 — verified forecast

Once the ledger contains an elapsed target week, open its genre page and use:
“This forecast called **[genre]** at **[prediction and interval]**. The realized
point was **[actual]**, and its rolling-origin MASE was **[score]**—a result
evaluated after prediction, not fitted afterward.”

The current artifact has no eligible example: it has three metric weeks against
an eight-week minimum and publishes no forecast. For a demo today, say:
“The validation gate is working; Soundcheck refuses to manufacture the
‘it worked’ slide before an out-of-sample result exists.”

### 0:24–0:36 — `/gap`

“The discovery gap is the novel metric. Positive means listening change is
outpacing music conversation—an acquisition opportunity. Negative means
social hype is outrunning listening change. Missing deltas stay missing; they
never become zero.”

### 0:36–0:48 — `/ecosystem`

“A creator tool can damage its own signal by sending everyone into one scene.
Entropy, effective genres, concentration, and scene churn ask whether the
content ecosystem is diversifying or narrowing as recommendations act on it.”

### 0:48–1:00 — `/methods`

“The methods page is part of the product. Every estimate exposes uncertainty,
small scenes shrink toward a weekly prior, every forecast faces persistence,
and raw posts, artists, and releases remain available as receipts.”

### Demo integrity rule

Replace the bracketed verified-forecast values only from an elapsed target in
the live backtest ledger. Until then, use the cold-start substitution exactly
as written. Never present a synthetic test, in-sample fit, or unelapsed target
as the verified forecast. Genre-neutral is the product direction, not a claim
that the current artifact covers every genre. Until cross-source gates are
implemented and passed, demonstrate only the current eligible set and describe
unsupported genres as `insufficient_evidence`.
