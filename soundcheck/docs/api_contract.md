# Soundcheck API Contract

**Status:** frozen through Phase 8, contract version `0.2.1`.

The Next.js frontend builds against this document, not DuckDB or Python
implementation details. Breaking field changes require a versioned API.
All endpoints are `GET`, all dates are ISO `YYYY-MM-DD`, and every `week`
value is the Monday beginning an ISO week.

The API reads only precomputed `mart_` and `fcst_` artifacts. It does not
calculate metrics, deltas, forecasts, evidence weights, or scene coordinates.
Responses are cached per worker for 60 seconds and include:

```http
Cache-Control: public, max-age=60
```

`null` means the source history cannot support that value. In particular,
first Last.fm observations never become zero deltas.

## Shared value shapes

Historical estimates use 90% Phase 4 confidence intervals. Forecasts use 80%
prediction intervals. Both serialize with the same structural shape while the
containing field states which uncertainty it represents:

```json
{
  "value": 1.12,
  "lower": 0.71,
  "upper": 1.54
}
```

Errors have a stable envelope:

```json
{
  "detail": {
    "code": "unknown_genre",
    "message": "Unknown canonical genre: not-a-genre"
  }
}
```

- Unknown canonical genre: `404`, code `unknown_genre`.
- Future ISO week: `422`, code `future_week`.
- A non-Monday `week`: `422`, code `invalid_iso_week`.
- Query parsing or bounds failure: `422`, code `validation_error`.
- Collection queries for an observed-empty or missing past week return `[]`.

## `GET /api/health`

Reports read-only datastore readiness and artifact recency.

```json
{
  "status": "ok",
  "datastore_mode": "read_only",
  "latest_metric_week": "2026-07-13",
  "latest_forecast_week": "2026-07-20",
  "latest_complete_week": "2026-07-13",
  "metric_rows": 189,
  "forecast_rows": 126,
  "last_pipeline_run": {
    "run_id": "gha-123456789-1",
    "run_kind": "weekly",
    "trigger": "schedule",
    "git_sha": "8c1afeb",
    "status": "success",
    "started_at": "2026-07-20T06:47:00Z",
    "completed_at": "2026-07-20T07:31:12Z",
    "wall_time_seconds": 2652.0,
    "rows_ingested": {
      "bluesky_posts": 412,
      "bluesky_engagement_snapshots": 358,
      "lastfm_tag_snapshots": 48,
      "lastfm_artist_snapshots": 4469,
      "musicbrainz_release_groups": 63
    },
    "resolution_posts_attempted": 301,
    "resolution_links_resolved": 267,
    "resolution_rate": 0.887,
    "metric_rows": 63,
    "forecast_rows": 126,
    "brief_rows": 6,
    "error_message": null
  },
  "cache_ttl_seconds": 60
}
```

Dates and `last_pipeline_run` can be `null` during cold start.
`latest_complete_week` is the most recent historical ISO week with a
publishable opportunity estimate; the website's global freshness stamp uses
this field. The run manifest reports rows observed inside the persisted run
window, not lifetime table sizes.

## `GET /api/genres/opportunities`

Query parameters:

- `week` — optional ISO-week Monday; defaults to the latest week with a
  non-null opportunity score.
- `limit` — integer `1..200`, default `50`.

Rows are ordered by opportunity descending. Shrinkage and effective sample size
are axis-specific because conversation uses beta-binomial shrinkage while
supply uses Gamma-Poisson shrinkage.

```json
[
  {
    "week": "2026-07-13",
    "genre": "shoegaze",
    "opportunity": {"value": 1.12, "lower": 0.71, "upper": 1.54},
    "discovery_gap": {"value": 0.42, "lower": 0.08, "upper": 0.79},
    "z_conversation": {"value": 0.63, "lower": 0.31, "upper": 0.94},
    "z_listening": {"value": 1.05, "lower": 0.72, "upper": 1.37},
    "z_supply": {"value": -0.28, "lower": -0.51, "upper": -0.06},
    "shrinkage_weight": {"conversation": 0.84, "supply": 0.61},
    "effective_n": {"conversation": 18.5, "supply": 4.0},
    "spike_flag": {
      "conversation": false,
      "listening": true,
      "supply": false
    },
    "breakout_flag": true
  }
]
```

## `GET /api/genres/{genre}/timeseries`

Query parameters:

- `weeks` — integer `1..260`, default `26`.

History is ascending by week. Forecasts are appended separately because their
uncertainty is an 80% prediction interval and each carries its own validation
record. When a skilled model exists, the selected skilled row is returned. If
none beats persistence, the naive row is returned as `no_skill`.

```json
{
  "genre": "shoegaze",
  "history": [
    {
      "week": "2026-07-13",
      "conversation": {
        "index": {"value": 0.63, "lower": 0.31, "upper": 0.94},
        "ewma": {"value": 0.48, "lower": 0.22, "upper": 0.76},
        "spike": false
      },
      "listening": {
        "index": {"value": 1.05, "lower": 0.72, "upper": 1.37},
        "ewma": {"value": 0.81, "lower": 0.54, "upper": 1.12},
        "spike": true
      },
      "supply": {
        "index": {"value": -0.28, "lower": -0.51, "upper": -0.06},
        "ewma": {"value": -0.14, "lower": -0.37, "upper": 0.08},
        "spike": false
      },
      "opportunity": {"value": 1.12, "lower": 0.71, "upper": 1.54},
      "discovery_gap": {"value": 0.42, "lower": 0.08, "upper": 0.79}
    }
  ],
  "forecasts": [
    {
      "target_week": "2026-07-20",
      "target_axis": "listening",
      "horizon": 1,
      "model": "lightgbm",
      "skill_status": "skill",
      "prediction_interval_80": {
        "value": 1.21,
        "lower": 0.58,
        "upper": 1.73
      },
      "backtest_mase": 0.72,
      "backtest_coverage_80": 0.78,
      "backtest_origins": 14
    }
  ]
}
```

`listening`, `opportunity`, and `discovery_gap` can be `null` where valid
consecutive Last.fm snapshots do not exist. `backtest_mase` is `null` when the
naive baseline has zero error; that forecast is explicitly `no_skill`.

## `GET /api/evidence/bluesky`

Query parameters:

- `week` — optional ISO-week Monday; defaults to the latest week containing
  publication-eligible Bluesky evidence.
- `limit` — integer `1..200`, default `50`.

This source feed is intentionally distinct from the resolved posts behind a
genre score. Collection remains broad for recall, including all configured
YouTube link facets. The weekly batch applies a stricter publication gate:
dedicated music services and explicit music hashtags or intents qualify
directly, while broad YouTube links require additional music context. This
keeps non-music videos in the append-only raw record without presenting them
as music discussion.

```json
[
  {
    "uri": "at://did:plc:example/app.bsky.feed.post/3abc",
    "did": "did:plc:example",
    "created_at": "2026-07-15T09:00:00Z",
    "text": "Herbie Hancock - Rain Dance\n#NP #Music",
    "link_urls": [],
    "hashtags": ["NP", "Music"],
    "matched_rules": ["hashtag:#np"],
    "likes": 12,
    "reposts": 4,
    "replies": 2
  }
]
```

These engagement counts are observed receipts, not estimates. An empty or
missing past week returns `[]`.

## `GET /api/genres/{genre}/evidence`

Query parameters:

- `week` — optional ISO-week Monday; defaults to the latest metric week.
- `limit` — integer `1..200`, default `20`, applied independently to each
  source list.

These are the receipts behind the corresponding `mart_.genre_weekly` row.
Listening values are already validated consecutive-snapshot deltas; the API
never derives them from lifetime totals.

```json
{
  "genre": "shoegaze",
  "week": "2026-07-13",
  "bluesky_posts": [
    {
      "uri": "at://did:plc:example/app.bsky.feed.post/3abc",
      "did": "did:plc:example",
      "created_at": "2026-07-15T09:00:00Z",
      "text": "Listening to Example Artist",
      "likes": 12,
      "reposts": 4,
      "replies": 2,
      "artist_name_raw": "Example Artist",
      "resolution_method": "direct_mbid",
      "resolution_score": 100.0,
      "join_key_type": "mbid"
    }
  ],
  "lastfm_artists": [
    {
      "artist_key": "mbid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "artist_name": "Example Artist",
      "artist_mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "playcount_delta": 1250,
      "listeners_delta": 84,
      "fetched_at": "2026-07-19T23:30:00Z"
    }
  ],
  "musicbrainz_releases": [
    {
      "release_group_mbid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "title": "Example Release",
      "artist_credits": [
        {
          "credit_name": "Example Artist",
          "artist_name": "Example Artist",
          "mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          "join_phrase": ""
        }
      ],
      "first_release_date": "2026-07-18",
      "types": ["Album"],
      "genres": ["shoegaze"]
    }
  ]
}
```

An empty genre-week returns the same object with three empty receipt lists.

## `GET /api/forecast/next-up`

Query parameters:

- `limit` — integer `1..200`, default `20`.

Only Phase 4 breakout precursors enter this ranking. Both the predicted
opportunity and its gain retain prediction intervals. Each axis exposes the
selected model and its backtest MASE.

```json
[
  {
    "origin_week": "2026-07-13",
    "target_week": "2026-07-20",
    "genre": "shoegaze",
    "rank": 1,
    "predicted_opportunity": {
      "value": 1.34,
      "lower": 0.62,
      "upper": 1.91
    },
    "predicted_gain": {
      "value": 0.22,
      "lower": -0.41,
      "upper": 0.79
    },
    "conversation_model": {"name": "ets", "mase": 0.81},
    "listening_model": {"name": "lightgbm", "mase": 0.72},
    "skill_status": "skill",
    "breakout_evidence_week": "2026-07-13"
  },
  {
    "origin_week": "2026-07-13",
    "target_week": "2026-07-20",
    "genre": "slowcore",
    "rank": 2,
    "predicted_opportunity": {
      "value": 0.75,
      "lower": -0.10,
      "upper": 1.43
    },
    "predicted_gain": {
      "value": 0.08,
      "lower": -0.64,
      "upper": 0.61
    },
    "conversation_model": {"name": "naive", "mase": 1.0},
    "listening_model": {"name": "naive", "mase": 1.0},
    "skill_status": "no_skill",
    "breakout_evidence_week": "2026-07-13"
  }
]
```

## `GET /api/ecosystem`

Query parameters:

- `weeks` — integer `1..260`, default `26`.

Rows are ascending by week. A metric and its full band are `null` together
when that week lacks enough listening or comparison history.

```json
[
  {
    "week": "2026-07-13",
    "listening_entropy": {"value": 3.12, "lower": 2.94, "upper": 3.27},
    "effective_genres": {"value": 22.65, "lower": 18.92, "upper": 26.31},
    "conversation_hhi": {"value": 0.073, "lower": 0.061, "upper": 0.088},
    "listening_top10_share": {
      "value": 0.58,
      "lower": 0.51,
      "upper": 0.64
    },
    "scene_churn_jaccard_4w": {
      "value": 0.42,
      "lower": 0.31,
      "upper": 0.54
    },
    "breakout_genres": ["shoegaze", "jungle"],
    "canonical_genre_count": 63,
    "listening_observed_genres": 51,
    "opportunity_observed_genres": 51
  }
]
```

## `GET /api/briefs`

Query parameters:

- `week` — optional ISO-week Monday.

Rows are stored template-generated A&R notes, never generated in the request
path and never produced by an LLM API. Only top-decile, positive-forecast
opportunities with sufficient effective sample size and complete cross-source
receipts are eligible. The default publishing floor is `effective_n >= 5` for
both conversation and supply; the batch also requires at least two rising
artists, one public conversation receipt, release-history context, and a
crowded embedding neighbor. If `week` is omitted, the latest brief week is
used.

```json
[
  {
    "brief_id": "2026-W29-shoegaze",
    "week": "2026-07-13",
    "genre": "shoegaze",
    "headline": "Shoegaze has room to move before the release lane fills",
    "opportunity": {"value": 1.12, "lower": 0.71, "upper": 1.54},
    "rationale": "Shoegaze closes the week at +1.12 opportunity (90% CI +0.71 to +1.54). The one-week read moves +0.22, with an 80% prediction interval of -0.41 to +0.79; the interval crosses zero, so treat the direction as promising rather than settled. On listening, Example Artist (+1,250 plays, +84 listeners) and Second Artist (+930 plays, +61 listeners) are doing the pulling. Conversation is still summed up best by “Listening to Example Artist again…” Last week brought 2 releases versus a typical 5 across the prior 8 weeks. Avoid chasing the crowded cues around dream pop and post-punk.",
    "recommended_actions": [
      "Build around the listening lift from Example Artist and Second Artist.",
      "Leave audible room from the more crowded dream pop and post-punk lanes."
    ],
    "evidence_uris": [
      "at://did:plc:example/app.bsky.feed.post/3abc",
      "https://www.last.fm/music/Example%20Artist",
      "https://musicbrainz.org/release-group/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    ],
    "created_at": "2026-07-20T12:00:00Z"
  }
]
```

An observed week with no briefs—or a week in which all candidates are
suppressed for thin evidence—returns:

```json
[]
```

## `GET /api/scene-map`

Returns the latest batch-computed two-dimensional UMAP projection. The API does
not import or run UMAP. `evidence_volume` is the exact count of post, artist,
and release receipts attached to that latest genre-week; it is not a modeled
estimate.

```json
[
  {
    "as_of_week": "2026-07-13",
    "genre": "shoegaze",
    "x": -2.41,
    "y": 4.08,
    "opportunity": {"value": 1.12, "lower": 0.71, "upper": 1.54},
    "discovery_gap": {"value": 0.42, "lower": 0.08, "upper": 0.79},
    "evidence_volume": 37
  }
]
```

`opportunity` and `discovery_gap` can be `null` during the listening cold
start. Coordinates remain available because they come from canonical genre
embeddings.

## Deployment contract

Each Uvicorn worker owns exactly one DuckDB connection opened with
`read_only=True`. The database artifact must already contain the Phase 4, 5,
and scene/evidence mart tables before the process starts.

CORS allows `http://localhost:3000`. Production sets
`SOUNDCHECK_PROD_ORIGIN` to its exact HTTP(S) origin; wildcards are not used.
`SOUNDCHECK_DB_PATH` can override the default
`data/soundcheck.duckdb`.
