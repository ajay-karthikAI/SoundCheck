# Forecasting

Soundcheck forecasts the next one and two ISO weeks of the conversation and
listening z-scores for every canonical genre. Forecast credibility comes from
expanding-window backtests, not in-sample fit. Every published estimate includes
an 80% prediction interval, the model's historical interval coverage, its MASE,
and the number of rolling origins behind that score.

## Models

Models are evaluated from simplest to most flexible:

1. **Naive persistence:** \(\hat y_{t+h}=y_t\). This is the required baseline
   and is always published beside a skilled model.
2. **Seasonal naive:** \(\hat y_{t+h}=y_{t+h-52}\), when a full prior ISO-week
   cycle exists.
3. **ETS:** per-genre additive damped-trend exponential smoothing. Annual
   additive seasonality is enabled only after two complete 52-week cycles;
   shorter histories do not support estimating it responsibly.
4. **LightGBM:** one global model pooled across genres. Separate point and
   0.10/0.90 quantile fits use target lags 1--4, conversation/listening/supply
   EWMA levels, spike flags, supply index, discovery gap, cosine similarity to
   the current top-ten trending-genre embedding centroid, target
   week-of-year, and categorical genre ID.

The pooled model's feature vector records both its forecast origin and latest
observed week. Validation rejects any vector whose latest observation is after
the origin.

## Rolling-origin protocol

For each axis and horizon, the first origin requires eight consecutive observed
weeks for that genre. The training window then expands one week at a time and
the origin advances exactly one week. For an origin \(t\) and horizon \(h\):

- features use observations no later than \(t\);
- global-model training targets are no later than \(t\);
- the held-out target is \(y_{t+h}\);
- missing listening observations break the per-genre history rather than being
  zero-filled.

This last point preserves the Last.fm snapshot invariant: first observations
produce no listening delta and therefore no listening forecast history.

For model \(m\), Soundcheck reports

\[
\mathrm{MASE}_m =
\frac{\operatorname{mean}_{o\in O_m}|y_o-\hat y_{m,o}|}
     {\operatorname{mean}_{o\in O_m}|y_o-\hat y_{\text{naive},o}|},
\]

using only rolling origins shared by the model and naive baseline. A score below
1 beats persistence. A zero naive error makes the scale undefined; that ledger
row is marked `zero_naive_scale`. It cannot support a skilled-model claim, but
the naive estimate is still published as `no_skill` with a null MASE, its
empirical coverage, and its interval.

Empirical 80% coverage is the fraction of held-out targets within each model's
published interval. The actual rate is reported without adjustment or
suppression even when it misses 0.80. The naive and ETS intervals use only
pre-origin residuals; LightGBM fits pooled 0.10 and 0.90 quantile models using
only training examples available at that origin.

## Selection and publication

Selection is independent for each genre, target axis, and horizon. The
non-naive model with the lowest backtested MASE is selected only when its MASE
is below 1. The naive forecast remains in `fcst_.predictions` as an explicit
baseline. If no candidate beats it, the naive row is published with
`skill_status = 'no_skill'`; Soundcheck never hides the failure.

`fcst_.backtest_ledger` contains every held-out forecast and result.
`fcst_.model_scores` contains the per-model aggregate MASE and interval
calibration. `fcst_.predictions` contains the future estimates and uncertainty.
The batch replaces all four Phase 5 artifacts in one DuckDB transaction.

Evidence lineage remains queryable rather than copied: every held-out outcome
keys to `mart_.genre_weekly` by `(canonical_genre, target_week)`, while every
future prediction keys to its as-of evidence row by
`(canonical_genre, origin_week)`. Those mart rows carry the raw Bluesky post
URIs, Last.fm artist keys, and MusicBrainz release-group MBIDs.

## Next up

The marquee ranking begins only with genres flagged as breakout precursors in
the latest Phase 4 ecosystem row. For each eligible genre, the selected
one-week-ahead conversation and listening forecasts imply

\[
\widehat{\mathrm{opportunity}}_{t+1} =
\frac{\hat z^\text{conversation}_{t+1}+\hat z^\text{listening}_{t+1}}{2}
-z^\text{supply}_{t}.
\]

The predicted opportunity interval combines both axis forecast bounds with
current supply uncertainty. The predicted gain subtracts the current
opportunity score, and its interval additionally includes current opportunity
uncertainty. A next-up row is still labeled `no_skill` unless both axis
forecasts beat their naive baselines.

Supply is held at its latest known z-score because Phase 5 forecasts only
conversation and listening. This is an explicit limitation, not a forecast of
next week's release supply.

## Current backtest result

Run `make forecast` to regenerate and print the complete JSON-lines
model-score ledger. The checked data currently has fewer than the required
eight consecutive weeks, so the honest result is:

| Result | Value |
|---|---:|
| Available mart history | 3 weeks |
| Minimum training history | 8 weeks |
| Scored model rows | 0 |
| Published prediction rows | 0 |
| Status | `insufficient_history` |

This empty ledger is expected during cold start. It prevents unvalidated
forecasts from reaching the product.

## What 12--26 weeks can and cannot support

Twelve to 26 weekly points can support short-horizon persistence comparisons,
a restrained trend estimate, and pooled cross-genre learning. It cannot
credibly establish annual seasonality, rare-event behavior, or stable
genre-specific model rankings. Backtests in this range have few rolling origins,
so MASE is volatile and prediction intervals are often wide. Genres with gaps
or newly available listening deltas remain cold starts. Soundcheck exposes the
origin count and empirical coverage so users can see those limits directly.
