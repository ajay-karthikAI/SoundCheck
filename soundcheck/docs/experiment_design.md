# Experiment design: opportunity briefs for creators

## Decision and estimand

Soundcheck implies a product intervention: show eligible creators a weekly,
evidence-linked brief about a genre where measured music conversation and
listening change are outrunning release supply. The experiment asks whether
access to that brief changes what artists release, without reducing release
quality or causing the ecosystem to collapse onto the same few genres.

Soundcheck's product scope is genre-neutral, with indie as the default
discovery lens. That direction does not make every genre eligible for this
experiment. A genre enters the brief pool only after music conversation,
listening change, and release supply clear published cross-source coverage
gates and its resolution quality is adequate. Genres that do not clear those
gates are `insufficient_evidence`; they are not zero-activity controls. An
indie-first launch is the appropriate initial rollout while broader genre
families are measured and validated under the same standard.

The primary estimand is the artist-level intention-to-treat effect of brief
eligibility:

\[
\operatorname{ITT}
=
E[Y_i(1)-Y_i(0)],
\]

where \(Y_i\) is the number of releases by artist \(i\) in genres that were
briefed to that artist during the following 28 days. Assignment, not brief
opening, defines treatment. This avoids post-treatment selection from comparing
artists who chose to read a brief with artists who did not.

### Hypotheses

- **Alternative \(H_1\):** brief eligibility increases releases in briefed
  genres per assigned artist per 28 days.
- **Null \(H_0\):** brief eligibility has no effect on that rate.

The confirmatory test is two-sided. A decrease is decision-relevant: a brief
could discourage work in a scene by making crowding or uncertainty salient.

## Population, assignment, and delivery

Eligible units are active artists who have released or saved a work in the
previous 90 days, can receive creator guidance, and have enough genre evidence
to match them to at least one publishable Soundcheck brief. Eligibility is
frozen before randomization. The eligible brief set, cross-source coverage
status, taxonomy version, and resolution-quality gate are also frozen before
assignment. Missing source evidence cannot be converted into a zero-valued
genre signal to make an artist eligible.

Artists are randomized 1:1 within pre-treatment strata:

- prior-28-day release count: zero, one, or two or more;
- creator tenure;
- historical primary-genre family;
- pre-period listener scale.

Treatment artists see one brief in their creator workspace and may receive the
platform's normal notification. Control artists see the existing creator
workspace. Assignment persists for the full 28-day measurement window. The
analysis includes every randomized artist, including creators who never open
the brief.

### Why artist-level randomization

The intervention changes a creator's production decision, so the creator is
the unit at which treatment and outcome both live. User-level randomization
would split listeners into treatment groups even though listeners neither
receive the brief nor control whether an artist releases. It would also expose
the same artist's release to treated and control listeners, contaminating the
contrast and answering a recommendation question rather than the intended
creator-success question.

If a platform account contains a stable band or team identifier, all members
must share one assignment. Otherwise collaborators could transmit a brief
across nominally separate artist accounts.

## Outcomes

### Primary metric

For each randomized artist:

\[
Y_i =
\sum_r
\mathbf 1(
  r\text{ was released within 28 days and maps to a genre brief assigned to }i
).
\]

The genre mapping must be versioned at assignment time. The numerator includes
zero for an artist with no qualifying release; it must not condition on
releasing. The main estimate is the covariate-adjusted difference in mean
counts with heteroskedasticity-robust standard errors. A Poisson or negative
binomial model is a sensitivity analysis, not a replacement for the directly
interpretable mean difference.

Useful diagnostic outcomes, declared secondary, are brief open rate, time to
first draft, time to release, and the share of artists with at least one
qualifying release. None can replace the primary metric after results are seen.

### Guardrails

Guardrails are reported with confidence intervals and tested for practically
important harm, not merely for \(p>0.05\).

1. **Total release volume:** all releases per randomized artist per 28 days.
   The brief should redirect or unlock creation, not suppress overall output.
2. **Listener engagement quality:** qualified listens per exposed release and,
   where the platform can measure them, completion, save, repeat-listen, and
   28-day returning-listener rates. Raw play volume alone can reward
   low-quality distribution.
3. **Genre diversity:** weekly Shannon entropy of listening share and its
   effective number of genres, exactly as defined in
   [metrics.md](metrics.md). The non-inferiority guardrail protects against
   every creator piling into the same apparent opportunity and destroying the
   diversity that produced the signal.

The experiment should pause for investigation if total release volume or
engagement quality crosses a pre-registered harm boundary. Diversity is
evaluated over several post-assignment weeks because ecosystem movement is
slower and noisier than an individual release decision.

## Power analysis

The arithmetic below is a planning calculation, not a result from Soundcheck's
current cold-start dataset. Replace the assumptions with internal platform
estimates before launch.

Assume:

| Quantity | Planning value |
|---|---:|
| Control mean \(\lambda_0\) | 0.20 releases per artist per 28 days |
| Minimum detectable effect \(\Delta\) | 0.04 releases |
| Relative lift | 20% |
| Two-sided \(\alpha\) | 0.05 |
| Power \(1-\beta\) | 0.80 |
| Overdispersion multiplier \(\phi\) | 1.50 |

Using the normal approximation for two independent Poisson means,

\[
n_{\text{per arm}}
\approx
\frac{(z_{1-\alpha/2}+z_{1-\beta})^2
      (\lambda_0+\lambda_1)}
     {(\lambda_1-\lambda_0)^2},
\]

with \(\lambda_1=0.24\), \(z_{0.975}=1.96\), and \(z_{0.80}=0.84\):

\[
n
=
\frac{(1.96+0.84)^2(0.20+0.24)}{0.04^2}
=
\frac{7.84\times0.44}{0.0016}
=
2{,}156\text{ artists per arm}.
\]

Allowing \(\phi=1.50\) for variance above the Poisson mean gives

\[
2{,}156\times1.50=3{,}234
\]

artists per arm, or 6,468 total. Add expected attrition only for outcomes that
can genuinely become unobservable; an artist who makes no release is an
observed zero, not attrition. The launch plan should recompute power from a
blinded pre-period estimate of the mean, variance, and stratum sizes.

## Interference and the two-sided platform

The no-interference assumption is fragile. Briefed creators may compete for the
same listeners, copy one another, collaborate with control artists, or increase
release supply enough to erase the opportunity. Recommendation systems can
then amplify those releases to both treatment and control listeners. The
artist-level ITT therefore estimates the effect of assigning briefs at the
tested saturation, not a timeless effect of a brief in isolation.

Pre-register three interference checks:

- treatment saturation among an artist's collaborators;
- treatment saturation within the assigned genre;
- the change in genre-level supply after briefs are issued.

Estimate direct and saturation effects if those exposures are available.
Otherwise report them as limitations and avoid extrapolating from a low-
saturation test to full rollout.

### Cluster randomization by genre

Randomizing whole genres is a cleaner fallback when cross-artist spillover
within a scene is expected to dominate. It sacrifices substantial power.
With a planning cluster size of \(m=80\) artists and intra-cluster correlation
\(\rho=0.02\), the design effect is

\[
\operatorname{DE}=1+(m-1)\rho=1+79(0.02)=2.58.
\]

The overdispersion-adjusted individual-randomization requirement becomes
\(3{,}234\times2.58=8{,}344\) artists per arm, or about 16,688 total. In an
illustrative planning pool of 63 eligible genres, a conservative split has 31
genres, or 2,480 artists, in the smaller arm. Its effective sample is only
\(2{,}480/2.58\approx961\) artists.
Under the same baseline and variance assumptions, the approximate detectable
lift rises to 0.076 releases per artist, about 38% rather than 20%.

The 63-genre pool is arithmetic for the power example, not a claim that 63
genres currently satisfy the v2 cross-source evidence gate. Actual cluster
counts and family composition must be recomputed from the frozen eligible set
before launch.

Genre-cluster assignment is therefore preferable only when interference makes
artist randomization scientifically misleading. Pair-match genre clusters on
pre-period release rate, listening share, conversation share, supply, and
embedding neighborhood before random assignment. Inference must use the genre
cluster, not the artist, as the independent unit.

## Analysis plan

1. Freeze the eligible population, brief set, genre-map version, primary
   metric, guardrail margins, exclusions, and analysis code before assignment.
2. Check assignment balance using standardized differences; do not use balance
   \(p\)-values to decide whether randomization “worked.”
3. Estimate the artist-level ITT with randomization-stratum fixed effects and
   pre-period release count as a precision covariate.
4. Report the absolute effect, relative effect, 95% confidence interval, and
   group means. Do not publish an effect without its interval.
5. Use randomization inference as a robustness check. For genre-cluster
   assignment, use pair-level fixed effects and cluster-robust or permutation
   inference over genre pairs.
6. Apply the pre-registered multiple-testing procedure to guardrails and
   secondary outcomes. The primary outcome remains a single confirmatory test.

## Causal appendix: does music conversation cause listening change?

The product's observational data can test temporal patterns, but it cannot by
itself turn conversation into an exogenous treatment. The following design is
a causal robustness program, not evidence that the assumption already holds.
Here, music conversation means qualifying public Bluesky activity, listening
change means deltas between consecutive Last.fm snapshots, and release supply
means first-release MusicBrainz release groups. None is a generic popularity
measure.

### Event-study difference in differences

Treat a conversation spike flag as an event for genre \(g\) in week \(T_g\).
The outcome is the following weeks' valid Last.fm listening delta or listening
index; lifetime totals and first snapshots remain excluded. For each event,
select non-spiked control genre-weeks using only pre-event data:

- four-week conversation and listening levels and slopes;
- release supply and release shocks;
- evidence volume and effective sample size;
- canonical-genre embedding distance.

Exclude controls with a spike in the event window and impose a washout between
events for the same genre. Estimate an interaction-weighted event study:

\[
Y_{gt}
=
\alpha_g+\lambda_t+
\sum_{k\ne-1}\beta_k
\mathbf 1[t-T_g=k]
+\gamma^\top X_{gt}
+\varepsilon_{gt}.
\]

Genre fixed effects absorb stable scene differences; ISO-week fixed effects
absorb common shocks. Cluster uncertainty by genre and, where the event count
supports it, use randomization-style inference over matched event sets.

The identifying assumption is conditional parallel trends: absent the
conversation spike, treated and matched control genres would have followed the
same listening trajectory. Probe it rather than merely state it:

- plot event-time coefficients for weeks \(-4\) through \(-2\);
- test those lead coefficients jointly;
- compare pre-period slopes and placebo event dates;
- repeat matching without post-event variables;
- report sensitivity to excluding release weeks and major artist events.

A pre-trend test with low power does not prove parallel trends. Visible leads,
anticipatory release promotion, or different pre-event slopes invalidate a
causal reading.

### Synthetic-control robustness

For well-observed spike events, construct a weighted combination of donor
genres that reproduces the treated genre's pre-event listening, conversation,
supply, and ecosystem path. Donors must have no spike near the event and no
obvious shared artist shock. Compare the post-event gap with in-time placebos
and leave-one-donor-out estimates. Synthetic control is useful when one large
event has a long pre-period; it is not credible with the current short history
or a weak donor pool.

### Honest limitations

Conversation spikes may be caused by the same release, playlist placement,
tour, scandal, or recommendation intervention that lifts listening. Bluesky
users and Last.fm scrobblers are selected populations, artist-to-genre
resolution is imperfect, MusicBrainz supply can arrive with a completeness
lag, and cross-genre spillovers violate a clean untreated condition. Weekly
aggregation obscures within-week ordering. Matching, fixed effects, and
synthetic controls cannot remove unmeasured common causes. A credible causal
claim ultimately needs an exogenous conversation intervention, randomized
promotion, or a defensible natural experiment.

Broader genre scope adds further transport risks: source participation,
taxonomy ambiguity, language coverage, baseline release rates, and spillover
patterns can differ substantially between indie, mainstream, regional, and
multilingual genres. An effect estimated in an indie-first rollout must not be
presented as a universal genre effect. Each newly enabled family needs adequate
cross-source coverage and a pre-specified analysis of treatment-effect
heterogeneity; genres without that evidence remain `insufficient_evidence`.
