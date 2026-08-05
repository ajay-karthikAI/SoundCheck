# Soundcheck metrics

This document defines the Phase 4 v1 statistical contract. The parallel
hierarchical contract is documented in
[taxonomy-v2 metrics](metrics_v2.md). All weeks are ISO
weeks in UTC, represented by their Monday `week_start`. All rows are rebuilt
idempotently from immutable `raw_` evidence and resolved `stg_` joins.

## Evidence attribution

Each `mart_.genre_weekly` row retains:

- `conversation_post_uris`, linking the conversation score to raw Bluesky
  posts and their latest AppView engagement snapshot;
- `listening_artist_keys`, linking listening growth to the exact Last.fm
  artist snapshot sequences; and
- `supply_release_group_mbids`, linking supply to MusicBrainz release groups.

Artists and releases may map to more than one canonical genre. They contribute
once to each distinct mapped genre, never more than once to the same
genre-week. Cross-genre totals therefore describe overlapping scenes rather
than a mutually exclusive taxonomy.

Conversation posts use the preferred staged artist link: MBID joins take
precedence over name joins. Engagement uses the latest available AppView poll
for the post, which is intended to be the approximately 72-hour observation.
Missing engagement is zero while the resolved post itself still contributes
one mention.

MusicBrainz release groups require a complete `YYYY-MM-DD` first-release date.
Partial dates cannot be assigned to an ISO week honestly and are excluded.

## Axis definitions

For genre \(g\) in week \(t\), raw conversation attention is

\[
C_{gt}
= M_{gt}
+ 0.5L_{gt}
+ 1.5R_{gt}
+ Q_{gt},
\]

where \(M\) is resolved-post mentions, \(L\) likes, \(R\) reposts, and \(Q\)
replies. Reposts receive the largest weight because a repost is an active
discovery act.

The observable listening score is

\[
A_{gt}
= \sum_{i \in g}
\left(\Delta P_{it} + 5\Delta U_{it}\right),
\]

where \(P\) is cumulative playcount and \(U\) is cumulative listeners.
New listeners receive more weight than repeat plays.

The supply count is

\[
S_{gt} = \#\{\text{release groups first released in }t\text{ and mapped to }g\}.
\]

Conversation and supply are empirical-Bayes adjusted as described below.
The three published indices are then

\[
z^C_{gt}
= z_t\!\left(\log(1+\widetilde C_{gt})\right),
\qquad
z^A_{gt}
= z_t\!\left(\log(1+A_{gt})\right),
\qquad
z^S_{gt}
= z_t\!\left(\log(1+\widetilde S_{gt})\right).
\]

The operator \(z_t\) uses the population mean and population standard
deviation of observed canonical genres within that week only. It never uses
global history. A constant observed vector receives zeros. Missing listening
observations remain missing and are not included in the weekly mean or
standard deviation.

## Last.fm snapshot deltas

Last.fm totals are lifetime cumulative counters, not listening events.
Snapshots are ordered within stable identity keys:

- `mbid:<lowercase-mbid>` when an MBID exists;
- otherwise `name:<casefolded-name>`.

Multiple observations for the same identity in one ISO week—including
same-week retries and duplicate identities returned by Last.fm
autocorrection—are collapsed to the latest observation before ordering. This
prevents an accidental re-poll minutes later from masquerading as weekly
growth. For a current weekly snapshot \(j\),

\[
\Delta P_j = P_j - P_{j-1},
\qquad
\Delta U_j = U_j - U_{j-1}.
\]

The delta is attributed to the ISO week containing the current snapshot.
The first observation has no predecessor and is excluded. If either counter
decreases, the interval is treated as a source correction and excluded rather
than clipped or zero-filled. Multiple valid intervals for the same artist and
week are summed before artists are used as bootstrap evidence units.

Consequences:

- a first collection correctly produces no listening metric;
- lifetime totals are never interpreted as weekly activity;
- a genre with no valid consecutive artist observations has `NULL` listening,
  opportunity, discovery gap, listening health, and listening trend values.

## Empirical Bayes: conversation share

Because the conversation weights occur in half-points, define integer
pseudo-counts \(u_{gt}=2C_{gt}\), weekly total \(N_t=\sum_g u_{gt}\), and raw
share \(p_{gt}=u_{gt}/N_t\). With \(G\) canonical genres, the symmetric
cross-genre prior mean is

\[
\mu_t = \frac{1}{G}.
\]

For the beta-binomial prior

\[
\theta_{gt}\sim\operatorname{Beta}(\alpha_t,\beta_t),
\qquad
u_{gt}\mid\theta_{gt}\sim\operatorname{Binomial}(N_t,\theta_{gt}),
\]

write the prior concentration as

\[
\kappa_t=\alpha_t+\beta_t,
\qquad
\alpha_t=\mu_t\kappa_t,
\qquad
\beta_t=(1-\mu_t)\kappa_t.
\]

The method-of-moments latent share variance removes the approximate binomial
sampling component:

\[
v_t
= \max\left(
\operatorname{Var}_g(p_{gt})
- \frac{\mu_t(1-\mu_t)}{N_t},
\epsilon
\right),
\]

\[
\widehat\kappa_t
= \operatorname{clip}\left(
\frac{\mu_t(1-\mu_t)}{v_t}-1,
\epsilon,
10^6
\right).
\]

The posterior share is

\[
\widehat\theta_{gt}
= \frac{u_{gt}+\alpha_t}{N_t+\kappa_t}
= (1-w_t)p_{gt}+w_t\mu_t,
\qquad
w_t=\frac{\kappa_t}{N_t+\kappa_t}.
\]

Thus shrinkage always moves toward the prior and cannot pass it. The adjusted
conversation score used by the index is

\[
\widetilde C_{gt}
= \frac{N_t\widehat\theta_{gt}}{2}.
\]

`conversation_effective_n` is \(N_t/2\), expressed in original weighted-score
units, and `conversation_shrinkage_weight` is \(w_t\). With no conversation
evidence, raw shares are zero, posterior shares equal \(1/G\), adjusted counts
remain zero, and the weekly index is the neutral all-zero vector.

## Empirical Bayes: supply counts

Supply uses a Gamma-Poisson model with one genre-week exposure:

\[
\lambda_{gt}\sim\operatorname{Gamma}(a_t,b_t),
\qquad
S_{gt}\mid\lambda_{gt}\sim\operatorname{Poisson}(\lambda_{gt}),
\]

where \(b_t\) is a rate. Let \(m_t\) and \(v_t\) be the across-genre mean and
population variance of raw supply counts. Since the marginal variance is
\(m_t+m_t^2/a_t\), the method-of-moments fit is

\[
\widehat a_t
= \frac{m_t^2}{v_t-m_t}
\quad\text{when }v_t>m_t,
\qquad
\widehat b_t=\frac{\widehat a_t}{m_t}.
\]

When the observed counts are not overdispersed, \(a_t\) is capped at \(10^6\),
representing a tightly concentrated weekly prior. The posterior rate is

\[
\widetilde S_{gt}
= \mathbb E[\lambda_{gt}\mid S_{gt}]
= \frac{a_t+S_{gt}}{b_t+1}
= w_t m_t + (1-w_t)S_{gt},
\qquad
w_t=\frac{b_t}{b_t+1}.
\]

Again, the posterior lies between the observation and the prior mean.
`supply_effective_n` is the one genre-week exposure and
`supply_shrinkage_weight` is \(w_t\).

## Opportunity and discovery gap

Demand is the mean of conversation and listening indices:

\[
D_{gt}=\frac{z^C_{gt}+z^A_{gt}}{2}.
\]

Opportunity is demand minus supply:

\[
O_{gt}=D_{gt}-z^S_{gt}.
\]

Swapping demand and supply negates the score. Positive opportunity means
attention is outrunning release supply.

Discovery gap is

\[
G_{gt}=z^A_{gt}-z^C_{gt}.
\]

A positive gap identifies listening that has not translated into social
conversation. A negative gap identifies hype outrunning observed listening.

Neither metric is calculated without a valid listening delta. Missing
listening is never replaced with zero.

## Bootstrap uncertainty

All published axis, opportunity, discovery-gap, trend, and ecosystem point
estimates carry 90% intervals. The batch performs 2,000 deterministic
bootstrap resamples within every genre-week:

- posts are the conversation evidence units;
- artists are the listening evidence units; and
- release groups are the supply evidence units.

Each replicate samples the cell's \(n\) evidence units with replacement,
recomputes sums, refits the weekly empirical-Bayes adjustments, and recomputes
the within-week z-scores. Opportunity and discovery gap are calculated from
the same replicate. The interval is the 5th and 95th percentile of the
replicate distribution. To guarantee the product never publishes a point
outside its own reported interval because of finite bootstrap asymmetry, the
percentile bounds are expanded only when necessary to include the point.

A cell with one evidence unit can have a degenerate interval. That accurately
states that the nonparametric bootstrap cannot learn sampling variation from
one unit; it does not claim the underlying process is certain.

## Trend layer

For each genre and axis, the exponentially weighted moving average has
halflife \(h=3\) weeks:

\[
\alpha=1-\exp\left(\frac{\log(0.5)}{h}\right),
\qquad
E_{gt}=\alpha z_{gt}+(1-\alpha)E_{g,t-1}.
\]

Bootstrap replicates pass through the same recursion to produce EWMA
intervals. Missing observations remain missing instead of carrying a stale
value forward.

For each week and axis, residuals are \(r_{gt}=z_{gt}-E_{gt}\). Their pooled
cross-genre population standard deviation is \(\sigma_t\). The axis spike
flag is

\[
r_{gt}>2.5\sigma_t.
\]

## Ecosystem health

For positive listening scores, \(q_{gt}=A_{gt}/\sum_g A_{gt}\):

\[
H_t=-\sum_g q_{gt}\log q_{gt},
\qquad
N^\mathrm{effective}_t=\exp(H_t).
\]

Uniform listening maximizes entropy at \(\log G\); a single-genre allocation
has zero entropy.

Conversation concentration uses raw conversation shares:

\[
\operatorname{HHI}_t=\sum_g p_{gt}^2.
\]

Listening concentration is the share of total listening score held by the ten
largest genres.

Scene churn compares the set \(T_t\) of the top 25 opportunity genres with the
set exactly four ISO weeks earlier:

\[
J_t=\frac{|T_t\cap T_{t-4}|}{|T_t\cup T_{t-4}|}.
\]

Low similarity means opportunity leadership is rotating quickly. It remains
missing when either comparison week lacks opportunity.

A breakout precursor is a genre at or above the week's 90th percentile of
the listening index and below the week's median conversation index. These are
quiet risers for the forecasting phase. The genre flag is stored in
`mart_.genre_weekly`; the corresponding genre list is stored in
`mart_.ecosystem_weekly`.

## Scene projection

The metrics batch projects the fixed canonical-genre `all-MiniLM-L6-v2`
embeddings to two dimensions with UMAP using cosine distance, `n_neighbors`
capped at 15, `min_dist = 0.1`, and a fixed random seed. At least three
embedded genres are required. Coordinates are stored in `mart_.scene_map`;
the serving layer never fits or transforms UMAP.

Each point carries the latest opportunity and discovery-gap intervals.
`evidence_volume` is an exact receipt count:

\[
V_{gt}=|\text{post URIs}|+|\text{artist keys}|+|\text{release MBIDs}|.
\]

It is used only as scene-map display volume and is not a cross-source demand
index.

## Current entity-resolution evaluation

The fixed evaluation fixture contains 60 examples and currently has no human
labels. Accordingly, `scripts/eval_resolution.py` reports zero labeled
examples, precision and recall as unavailable, and does not enforce the
quality thresholds. This is an incomplete validation state, not evidence of
either perfect or failed resolution. Precision and recall may be published
only after the fixture has been labeled independently of model predictions.
