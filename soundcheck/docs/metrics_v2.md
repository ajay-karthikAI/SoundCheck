# Taxonomy-v2 Metrics

## Scope and Isolation

Taxonomy-v2 metrics answer the same product questions as v1 while making
broad and niche genres comparable without pretending their raw volumes are
alike. They are batch-computed alongside v1. The batch never deletes, updates,
or reinterprets `mart_.genre_weekly`, `mart_.ecosystem_weekly`, or another v1
row.

Every v2 table is keyed by `taxonomy_version`. Rebuilding one version replaces
only rows carrying that version. Other v2 versions and all v1 history remain
unchanged. Weeks are ISO weeks in UTC, represented by Monday `week_start`.

## Eligibility and Missingness

`mart_.genre_coverage_v2` is the authoritative grid. A taxonomy genre appears
for every observed week even when its metrics cannot be estimated.

Only `coverage_state = ready` can enter an estimate. The batch also verifies
that conversation, a valid listening delta, and supply evidence are present.
A disagreement between a `ready` row and the loaded evidence becomes
`evidence_mismatch`.

For a non-ready or mismatched genre-week, raw and shrunk axes, effective
sample sizes, shrinkage weights, both z-score contexts, uncertainty, EWMA,
spikes, breakouts, opportunity, and discovery gap are all `NULL`. The coverage
and estimate states remain explicit. Receipt IDs may remain attached for
auditing. Missing evidence is never zero-filled or admitted to a z-score
population.

Operational maturity is an additional gate, independent of coverage. A v2
genre-week cannot become estimate-eligible until its 72-hour AppView
engagement, consecutive-week Last.fm delta, and fully collected closed
MusicBrainz window are all complete. The batch records
`conversation_pending`, `listening_pending`, and `supply_pending` explicitly in
`mart_.genre_week_axis_maturity`; any pending axis keeps decision estimates
null. The open current ISO week is always observational `supply_pending`.

## Weighted Evidence Attribution

Let \(m_{ag}\in(0,1]\) be artist \(a\)'s v2 membership weight for genre \(g\).

### Conversation

A resolved post inherits its linked artist's membership:

\[
C_{p,g}=m_{ag}\left(1+0.5L_p+1.5R_p+Q_p\right).
\]

The genre-week score is \(C_{g,t}=\sum_p C_{p,g}\). Every post URI remains a
receipt. Preferred post-artist links are MBID-first, then name fallback.

### Listening change

Last.fm totals are cumulative lifetime counters. Snapshots are collapsed to
the latest observation per MBID-first artist and ISO week, then ordered. Every
retained pair carries `previous_fetched_at`, `fetched_at`, exact
`interval_days`, and `listening_window_status`. For current snapshot \(j\):

\[
\Delta P_j=P_j-P_{j-1},\qquad
\Delta U_j=U_j-U_{j-1}.
\]

Only `listening_window_status = valid_weekly` enters the estimate: both rows
must be append-only observations, the prior row must be from the immediately
preceding ISO week, the current timestamp must be later, and both counters must
be monotone. First observations, same-week duplicates, nonconsecutive and
missing-week pairs, invalid order, and source corrections remain audit rows but
are excluded. Nothing is clipped, zero-filled, or time-normalized. In
particular, an 11-day delta is not divided into synthetic daily or weekly
values.

\[
A_{g,t}
=\sum_a m_{ag}\left(\Delta P_{a,t}+5\Delta U_{a,t}\right).
\]

The factor five preserves the decision that new listeners are stronger
discovery evidence than repeat consumption.

### Release supply

For release group \(r\), duplicate credited-artist evidence is collapsed to
the maximum membership per genre, then normalized across the release:

\[
s_{r,g}
=\frac{\max_{a\in r}m_{ag}}
{\sum_h\max_{a\in r}m_{ah}},
\qquad
S_{g,t}=\sum_r s_{r,g}.
\]

One release therefore contributes total mass one while retaining multi-genre
membership. Only complete MusicBrainz first-release dates enter a week.

## Effective Sample Size

Every eligible axis publishes Kish effective sample size:

\[
n_{\mathrm{eff}}
=\frac{\left(\sum_iw_i\right)^2}{\sum_iw_i^2}.
\]

Posts, valid artist intervals, and release groups are the respective evidence
units. Equal weights reduce to the unit count; unequal memberships reduce the
effective sample. Listening is not empirical-Bayes shrunk, so its shrinkage
weight is zero, while its effective artist count remains visible.

## Hierarchical Conversation Shrinkage

Define pseudo-counts \(u_g=2C_g\). Let \(f(g)\) be genre \(g\)'s family,
\(F\) the number of eligible families, and \(G_f\) eligible genres in family
\(f\). Week subscripts are suppressed.

### Family to weekly global prior

\[
U_f=\sum_{g\in f}u_g,\quad
N=\sum_fU_f,\quad
p_f=U_f/N,\quad
\mu_0=1/F.
\]

The beta-binomial method-of-moments fit is:

\[
v_0=\max\left(
\operatorname{Var}_f(p_f)-\frac{\mu_0(1-\mu_0)}{N},
\epsilon
\right),
\]

\[
\kappa_0=\operatorname{clip}\left(
\frac{\mu_0(1-\mu_0)}{v_0}-1,\epsilon,10^6
\right),
\quad
w_{f\to0}=\frac{\kappa_0}{N+\kappa_0},
\]

\[
\widehat\pi_f=(1-w_{f\to0})p_f+w_{f\to0}\mu_0.
\]

The family-balanced global prior is deliberate: one high-volume mainstream
family does not define the prior for every niche family.

### Subgenre to macro-family prior

\[
\phi_{g|f}=u_g/U_f,\qquad \mu_f=1/G_f.
\]

Applying the same method-of-moments fit inside \(f\) gives concentration
\(\kappa_f\):

\[
w_{g\to f}=\frac{\kappa_f}{U_f+\kappa_f},
\]

\[
\widehat\phi_{g|f}
=(1-w_{g\to f})\phi_{g|f}+w_{g\to f}\mu_f.
\]

The coherent posterior genre share and adjusted score are:

\[
\widehat\theta_g=\widehat\pi_f\widehat\phi_{g|f},
\qquad
\widetilde C_g=N\widehat\theta_g/2.
\]

Posterior genre shares sum to one. Each level moves toward its prior without
overshooting. The reported combined weight is:

\[
w_g^\ast
=1-(1-w_{g\to f})(1-w_{f\to0}).
\]

Both component weights are also stored.

## Hierarchical Supply Shrinkage

Let the family mean genre rate be:

\[
r_f=\frac{1}{G_f}\sum_{g\in f}S_g.
\]

Across families, let \(m_0\) and \(v_0\) be the mean and population variance:

\[
a_0=
\begin{cases}
m_0^2/(v_0-m_0),&v_0>m_0,\\
10^6,&v_0\le m_0,
\end{cases}
\qquad b_0=a_0/m_0.
\]

The family rate shrunk toward the weekly global rate is:

\[
\widehat m_f=\frac{a_0+r_f}{b_0+1},
\qquad
w_{f\to0}^{S}=\frac{b_0}{b_0+1}.
\]

Inside family \(f\), use \(\widehat m_f\) as the prior mean. With observed
within-family variance \(v_f\):

\[
a_f=
\begin{cases}
\widehat m_f^2/(v_f-\widehat m_f),&v_f>\widehat m_f,\\
10^6,&v_f\le\widehat m_f,
\end{cases}
\qquad b_f=a_f/\widehat m_f.
\]

\[
\widetilde S_g=\frac{a_f+S_g}{b_f+1},
\qquad
w_{g\to f}^{S}=\frac{b_f}{b_f+1}.
\]

The combined supply weight uses the same two-level expression as
conversation. A measured zero and missing supply remain distinct because only
coverage-ready rows enter the hierarchy.

## Global and Peer-Family Comparisons

Transform the eligible axes:

\[
x^C_g=\log(1+\widetilde C_g),\quad
x^A_g=\log(1+A_g),\quad
x^S_g=\log(1+\widetilde S_g).
\]

The global context is:

\[
z^{k,\mathrm{global}}_{g,t}
=\frac{x^k_{g,t}-\overline{x^k_t}}{\sigma^k_t}.
\]

The peer context is:

\[
z^{k,\mathrm{peer}}_{g,t}
=\frac{x^k_{g,t}-\overline{x^k_{f,t}}}{\sigma^k_{f,t}},
\qquad g\in f.
\]

Both use only the same ISO week. Global z-scores sum to approximately zero
within the week; peer z-scores sum to approximately zero within each
family-week. A constant or one-genre comparison receives zero. No value is
standardized across historical weeks.

## Opportunity and Discovery Gap

For context \(c\in\{\mathrm{global},\mathrm{peer}\}\):

\[
D^c_{g,t}=(z^{C,c}_{g,t}+z^{A,c}_{g,t})/2,
\]

\[
O^c_{g,t}=D^c_{g,t}-z^{S,c}_{g,t},
\qquad
G^c_{g,t}=z^{A,c}_{g,t}-z^{C,c}_{g,t}.
\]

Global opportunity compares all eligible genres. Peer opportunity compares
within the broad family. Positive discovery gap means listening change is
ahead of music conversation; negative means conversation is ahead.

Opportunity and discovery gap are `NULL` whenever no valid weekly listening
window survives for the genre-week, even if conversation and supply are
present. Corrected v2 metrics are derivation-versioned independently of
`taxonomy_version`; legacy v2 tables and other derivations remain unchanged.
Only a validated active derivation is read by production surfaces.

Ranked surfaces select the latest complete eligible ISO week strictly before
the current UTC week. Partial current-week evidence is observational only.

## Uncertainty

Every eligible axis, opportunity, discovery gap, EWMA, and ecosystem point has
a 90% interval. The batch performs 2,000 deterministic within-cell bootstrap
resamples of weighted posts, valid artist deltas, and release groups.

Every replicate refits both empirical-Bayes levels and recomputes both
within-week z-score contexts. Derived metrics use the same replicate. Bounds
are the 5th and 95th percentiles, expanded only when finite-bootstrap
asymmetry would otherwise exclude the point. A one-unit degenerate interval
states the nonparametric bootstrap's limitation, not underlying certainty.

## Trend, Spike, and Breakout Layers

For each axis and context:

\[
\alpha=1-\exp(\log(0.5)/3),
\qquad
E_{g,t}=\alpha z_{g,t}+(1-\alpha)E_{g,t-1}.
\]

Missing weeks remain missing. Bootstrap paths form EWMA intervals. With
residual \(r_{g,t}=z_{g,t}-E_{g,t}\), global spikes use the week's pooled
eligible-genre standard deviation; peer spikes use the family-week standard
deviation:

\[
r_{g,t}>2.5\sigma.
\]

Breakout precursors are at or above the 90th listening-z percentile and below
the median conversation z-score. Global and peer-family flags are stored.

## Macro-Family and Ecosystem Measures

`mart_.macro_family_weekly_v2` publishes eligible and total genre counts,
counts of each coverage state, raw axis totals, effective sample sizes, and
global and peer breakout lists. Its axis, opportunity, discovery-gap, EWMA,
interval, and spike estimates are global comparisons across eligible families.

`mart_.ecosystem_weekly_v2` has one global row across eligible genres and one
local row per macro family. For listening share \(q_g\):

\[
H=-\sum_gq_g\log q_g,\qquad N_{\mathrm{effective}}=\exp(H).
\]

Conversation concentration is \(\operatorname{HHI}=\sum_gp_g^2\). The global
row publishes top-10 listening share; family rows publish top-3 share, so
mainstream volume cannot flatten within-family movement.

Churn is Jaccard similarity between the scope's top-25 opportunity genres and
the same scope four ISO weeks earlier. It remains `NULL` without both weeks.
All ecosystem points carry bootstrap intervals.

## Storage and Running

Phase F creates only:

- `mart_.genre_weekly_v2`;
- `mart_.metric_estimates_v2`;
- `mart_.macro_family_weekly_v2`; and
- `mart_.ecosystem_weekly_v2`.

The estimate table is long-form by scope, context, and metric so uncertainty
cannot be separated from its point. The current FastAPI and frontend remain
on v1.

Run:

```bash
make metrics-v2
```

The command refreshes version-matched coverage, builds and replaces only the
configured taxonomy version, then prints global and peer opportunity
rankings, coverage-state counts, and row totals. When no genre clears the
coverage gate, both rankings explicitly report `unavailable`.

## Assumptions and Limitations

- Membership weights allocate evidence; they are not probabilities of an
  artist's essential identity.
- Current v2 memberships are applied to retained historical evidence. A
  taxonomy change requires a new versioned rebuild.
- The family-balanced conversation prior deliberately gives niche families
  prior standing not proportional to mainstream volume.
- Coverage cannot correct source demographic bias or MusicBrainz completeness
  lag.
- Last.fm deltas describe change among Last.fm users, not all listeners.
- Peer comparisons can be unstable with few eligible genres; effective sample
  size and intervals remain mandatory.
