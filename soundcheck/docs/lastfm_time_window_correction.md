# Last.fm time-window correction report

## Validated artifact

- Derivation version: `lastfm_weekly_v2`
- Recomputed at: 2026-08-06 UTC
- Legacy v1 rows preserved: 315, including 63 legacy opportunity rows
- Legacy taxonomy-v2 rows preserved: 645
- Corrected production opportunity rows: 0 in v1 and 0 in taxonomy v2
- Taxonomy-v2 withdrawals: 0; its coverage gate had already withheld these
  estimates even though its candidate/receipt path still required correction

The current collection has Last.fm observations in ISO weeks beginning
2026-07-20 and 2026-08-03, with 2026-07-27 missing. The exact elapsed interval
between the retained weekly snapshots is 11.0095049407 days. All 4,306 distinct
second-window artist pairs in both metric versions are therefore
`nonconsecutive_weeks`; none is divided or otherwise rescaled.

The materialized mapping audit contains:

| Artifact | Status | Mapping rows | Distinct artist-week pairs |
| --- | --- | ---: | ---: |
| v1 | `first_observation` | 34,701 | 11,387 |
| v1 | `nonconsecutive_weeks` | 17,957 | 4,306 |
| v2 | `first_observation` | 43,034 | 11,386 |
| v2 | `nonconsecutive_weeks` | 18,851 | 4,306 |

## Withdrawn v1 display rows

Every row below was previously displayed for ISO week 2026-08-03 and is now
withheld because its listening window is not `valid_weekly`. Values are the
preserved legacy point estimates; the corrected opportunity and discovery gap
are `NULL`.

| Week | Genre | Previous opportunity | Previous discovery gap | Reason |
| --- | --- | ---: | ---: | --- |
| 2026-08-03 | alt-country | 0.265793 | 0.613802 | `listening_window_not_valid_weekly` |
| 2026-08-03 | alternative rock | 2.242828 | -0.287147 | `listening_window_not_valid_weekly` |
| 2026-08-03 | ambient | 0.982998 | -0.100146 | `listening_window_not_valid_weekly` |
| 2026-08-03 | art rock | 0.244333 | 0.570882 | `listening_window_not_valid_weekly` |
| 2026-08-03 | bedroom pop | 0.443630 | 0.969476 | `listening_window_not_valid_weekly` |
| 2026-08-03 | black metal | -2.397898 | -1.951725 | `listening_window_not_valid_weekly` |
| 2026-08-03 | breakcore | 0.046843 | 0.175901 | `listening_window_not_valid_weekly` |
| 2026-08-03 | chillwave | 0.303205 | 0.280385 | `listening_window_not_valid_weekly` |
| 2026-08-03 | coldwave | -2.335774 | 0.007918 | `listening_window_not_valid_weekly` |
| 2026-08-03 | dark ambient | 0.054788 | -0.384089 | `listening_window_not_valid_weekly` |
| 2026-08-03 | darkwave | -2.056893 | -0.150027 | `listening_window_not_valid_weekly` |
| 2026-08-03 | doom metal | 0.043217 | -1.475448 | `listening_window_not_valid_weekly` |
| 2026-08-03 | downtempo | -0.150329 | 0.039200 | `listening_window_not_valid_weekly` |
| 2026-08-03 | dream pop | 0.684021 | 1.450258 | `listening_window_not_valid_weekly` |
| 2026-08-03 | drone | -0.099926 | -0.336154 | `listening_window_not_valid_weekly` |
| 2026-08-03 | drum and bass | 0.439423 | 0.742544 | `listening_window_not_valid_weekly` |
| 2026-08-03 | dungeon synth | -1.844536 | -1.149727 | `listening_window_not_valid_weekly` |
| 2026-08-03 | electronic | -1.172819 | -0.008332 | `listening_window_not_valid_weekly` |
| 2026-08-03 | electropop | 0.988176 | 1.332519 | `listening_window_not_valid_weekly` |
| 2026-08-03 | emo | 0.472090 | 1.284039 | `listening_window_not_valid_weekly` |
| 2026-08-03 | experimental | -0.561988 | -0.393374 | `listening_window_not_valid_weekly` |
| 2026-08-03 | experimental hip hop | -0.691625 | 1.156097 | `listening_window_not_valid_weekly` |
| 2026-08-03 | folk | 0.644722 | 0.385347 | `listening_window_not_valid_weekly` |
| 2026-08-03 | folk punk | -0.649418 | -0.243270 | `listening_window_not_valid_weekly` |
| 2026-08-03 | footwork | -0.553156 | 0.508188 | `listening_window_not_valid_weekly` |
| 2026-08-03 | garage rock | -0.258949 | 1.096601 | `listening_window_not_valid_weekly` |
| 2026-08-03 | glitch pop | 0.554474 | -0.293525 | `listening_window_not_valid_weekly` |
| 2026-08-03 | gothic rock | 0.313965 | -0.496565 | `listening_window_not_valid_weekly` |
| 2026-08-03 | grime | -1.023911 | -2.541488 | `listening_window_not_valid_weekly` |
| 2026-08-03 | hardcore punk | 0.682496 | -0.590639 | `listening_window_not_valid_weekly` |
| 2026-08-03 | hip hop | -1.730331 | -0.012325 | `listening_window_not_valid_weekly` |
| 2026-08-03 | house | 0.126968 | 1.309501 | `listening_window_not_valid_weekly` |
| 2026-08-03 | hyperpop | 0.363042 | 1.781649 | `listening_window_not_valid_weekly` |
| 2026-08-03 | indie folk | 0.026431 | 1.667361 | `listening_window_not_valid_weekly` |
| 2026-08-03 | indie pop | 1.156528 | 1.533228 | `listening_window_not_valid_weekly` |
| 2026-08-03 | indie rock | 2.358881 | -0.252583 | `listening_window_not_valid_weekly` |
| 2026-08-03 | industrial | 0.328030 | -0.746412 | `listening_window_not_valid_weekly` |
| 2026-08-03 | jungle | -0.515307 | 0.583884 | `listening_window_not_valid_weekly` |
| 2026-08-03 | krautrock | 0.466068 | -2.352536 | `listening_window_not_valid_weekly` |
| 2026-08-03 | lo-fi | -1.253457 | 0.980685 | `listening_window_not_valid_weekly` |
| 2026-08-03 | math rock | -0.333899 | -0.327939 | `listening_window_not_valid_weekly` |
| 2026-08-03 | metal | 0.801037 | -0.353555 | `listening_window_not_valid_weekly` |
| 2026-08-03 | midwest emo | -0.650322 | 1.238702 | `listening_window_not_valid_weekly` |
| 2026-08-03 | new wave | 1.423388 | -1.524949 | `listening_window_not_valid_weekly` |
| 2026-08-03 | noise rock | 0.384632 | -0.249238 | `listening_window_not_valid_weekly` |
| 2026-08-03 | other | -2.329755 | -0.296941 | `listening_window_not_valid_weekly` |
| 2026-08-03 | pop | 2.001370 | 0.447957 | `listening_window_not_valid_weekly` |
| 2026-08-03 | post-punk | 1.437618 | -1.496491 | `listening_window_not_valid_weekly` |
| 2026-08-03 | post-rock | 0.259303 | -0.261221 | `listening_window_not_valid_weekly` |
| 2026-08-03 | psychedelic rock | -0.708364 | -0.983071 | `listening_window_not_valid_weekly` |
| 2026-08-03 | punk rock | 0.912595 | -0.240953 | `listening_window_not_valid_weekly` |
| 2026-08-03 | r&b | 0.560096 | -0.004303 | `listening_window_not_valid_weekly` |
| 2026-08-03 | rock | 1.953297 | 0.173787 | `listening_window_not_valid_weekly` |
| 2026-08-03 | sadcore | 0.713327 | -1.581822 | `listening_window_not_valid_weekly` |
| 2026-08-03 | shoegaze | 0.391958 | 0.647616 | `listening_window_not_valid_weekly` |
| 2026-08-03 | slowcore | 0.972552 | -1.245139 | `listening_window_not_valid_weekly` |
| 2026-08-03 | synthpop | 0.842614 | 1.041396 | `listening_window_not_valid_weekly` |
| 2026-08-03 | synthwave | -2.101843 | -0.239926 | `listening_window_not_valid_weekly` |
| 2026-08-03 | techno | 0.111097 | -0.103830 | `listening_window_not_valid_weekly` |
| 2026-08-03 | trip-hop | -0.099627 | 0.140604 | `listening_window_not_valid_weekly` |
| 2026-08-03 | uk garage | -0.738281 | 1.062783 | `listening_window_not_valid_weekly` |
| 2026-08-03 | vaporwave | -2.492637 | -0.707611 | `listening_window_not_valid_weekly` |
| 2026-08-03 | witch house | -0.246788 | 0.160186 | `listening_window_not_valid_weekly` |
