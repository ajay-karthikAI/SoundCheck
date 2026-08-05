# Forecasting v2

Forecast v2 predicts the next one and two ISO weeks of the taxonomy-v2
conversation and listening indices. It evaluates both comparison contexts:
the genre's global within-week z-score and its within-macro-family peer
z-score. It is stored beside forecast v1; no v1 prediction or score ledger is
read, rewritten, or used to confer skill.

The batch is run with:

```bash
make forecast-v2
```

The command prints every row in the v2 model-score ledger as JSONLines,
including unavailable and cold-start rows, followed by a status summary.

## Models

The candidate set remains deliberately small:

1. **Naive persistence:** \(\hat y_{t+h}=y_t\). This is the mandatory
   baseline.
2. **Seasonal naive:** \(\hat y_{t+h}=y_{t+h-52}\), only when the matching
   prior-cycle observation exists.
3. **ETS:** a per-genre additive, damped-trend exponential-smoothing model.
   Annual seasonality is enabled only after two complete 52-week cycles.
4. **Global LightGBM:** a pooled model across all genres and macro families.
   Separate point, 0.10-quantile, and 0.90-quantile fits produce the point and
   nominal 80% interval.

“Global LightGBM” describes model pooling, not validation pooling. The model
may learn shared structure across families, but its skill is accepted only
after it beats naive in the forecasted genre's own validation group and its
current macro-family/popularity group.

## Features and leakage boundary

The target-axis inputs are the as-of value and three earlier lags. Other
time-varying inputs are conversation, listening, and supply EWMAs; spike flags;
current supply and discovery gap; and the origin-week means and observed genre
count for the macro family. Known calendar input is the target ISO
week-of-year.

Stable categorical inputs are genre ID, macro-family ID, parent genre ID,
taxonomy version, comparison context, and the popularity tier assigned at the
origin. Popularity tiers are low, middle, and high thirds of origin-week
effective evidence within the macro family; missing evidence is `unknown`.
Tier assignment never reads a target-week volume.

Every feature vector records `origin_week` and `max_observed_week`. The model
contract rejects `max_observed_week > origin_week`. Global LightGBM training
at origin \(t\) includes only examples whose targets are at or before \(t\).
The held-out value at \(t+h\) is never a feature or training target for that
origin.

## Rolling-origin protocol

Validation uses an expanding window, one-week steps, and horizons one and two.
A genre-axis-context needs at least eight consecutive, non-null metric weeks at
an origin. Missing estimates break the history. This is important for
listening: Last.fm first snapshots remain absent because only deltas between
consecutive cumulative snapshots are valid.

Each held-out row records:

- taxonomy version;
- genre and macro family;
- popularity tier at the origin;
- global or peer-family context;
- conversation or listening axis;
- horizon and model;
- training date range and valid week count;
- maximum feature week;
- actual, prediction, interval, error, and interval hit.

This produces two score views:

- `genre`: one genre in the popularity tier it occupied at those origins;
- `family_popularity`: all matching origins inside one macro family and
  popularity tier.

Both remain split by context, axis, horizon, model, and taxonomy version.

## MASE, coverage, and selection

For a model \(m\), using origins shared with persistence,

\[
\operatorname{MASE}_m =
\frac{\operatorname{mean}_{o \in O_m}|y_o-\hat y_{m,o}|}
     {\operatorname{mean}_{o \in O_m}|y_o-\hat y_{\mathrm{naive},o}|}.
\]

A non-naive model is eligible only when both its current genre-tier MASE and
current family-tier MASE are below 1. This prevents a result learned or
validated on the indie-heavy history from being transferred as a skill claim
to a new family. The eligible model with the lowest genre-tier MASE is selected.
If none qualifies, persistence is published with `forecast_status =
'no_skill'`.

Empirical interval coverage is the fraction of held-out actuals inside the
nominal 80% intervals. Actual coverage is published even when it is far from
0.80. Each publishable row includes the selected model's genre and family MASE
and coverage plus the naive point, interval, MASE, and coverage. When the naive
error scale is zero, MASE is mathematically undefined and remains null with
`score_status = 'zero_naive_scale'`; it is never converted to a favorable
skill score.

## Cold starts and missing evidence

Eight weeks is a minimum training threshold, not a guarantee that enough
held-out origins exist to validate a claim. Until a genre has the minimum
consecutive history **and** a scored naive ledger in its relevant family-tier
group, its row is:

```text
forecast_status = insufficient_history
model_name = null
prediction = null
interval_low = null
interval_high = null
backtest_mase = null
backtest_coverage_80 = null
```

Rejected or source-unsupported genres are `insufficient_evidence`. These states
are published as rows, not hidden and not represented by zero.

## DuckDB artifacts

All tables are under `fcst_` and include `taxonomy_version`:

- `backtest_ledger_v2`: every held-out forecast and its as-of provenance;
- `model_scores_v2`: complete scored and unscored genre and family-tier
  ledger;
- `predictions_v2`: one current status or forecast per
  genre/context/axis/horizon.

The v2 batch transaction deletes and replaces only the requested taxonomy
version in these three tables. The v1 tables `backtest_ledger`,
`model_scores`, `predictions`, and `next_up` are untouched.

## Honest limitations

- Twelve to twenty-six valid weeks can support short-horizon trend validation,
  but not deep annual seasonality. Seasonal naive is usually unavailable until
  week 52 and annual ETS seasonality until week 104.
- Eight observations permit model fitting but provide very few rolling-origin
  tests. MASE and coverage can be unstable, especially at horizon two.
- Nominal 80% intervals are not guaranteed to achieve 80% empirical coverage.
  Sparse residual histories can produce narrow intervals; the published
  empirical rate is the warning, not a claim of calibration.
- Family-tier validation reduces false portability but also reduces sample
  size. A genuinely useful model may remain `no_skill` because its relevant
  family lacks evidence.
- The global model can share statistical structure, not cultural meaning.
  Taxonomy labels, multilingual mappings, and source coverage can still encode
  uneven measurement quality.
- Global and peer-family z-scores are relative weekly measures. Forecasts
  predict movement in relative position, not raw streams, unique listeners,
  or market size.
- A taxonomy revision is a new validation population. Skill from another
  taxonomy version is never inherited.
