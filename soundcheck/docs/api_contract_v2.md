# Soundcheck Read API v2

Status: frozen for Expansion Phase H.

Base path: `/api/v2`

Version 2 is additive. It does not rename, remove, or change any endpoint or
payload under `/api`. The v1 contract remains frozen in
[`api_contract.md`](api_contract.md).

The examples below are illustrative contract fixtures, not live findings.
OpenAPI is available at `/openapi.json`.

## Contract rules

- All endpoints are `GET` and read only.
- All timestamps are UTC ISO 8601 values. Every `week` is the Monday that
  begins an ISO week.
- `taxonomy_version` defaults to the deployed taxonomy version. This release
  supports `2.0.0`.
- `context` is `global` or `peer_family`. Global values compare genres with
  all eligible genres in the same week. Peer-family values compare a genre
  only with eligible genres in its macro family in the same week.
- Every genre-bearing item contains the stable `genre_id`, `slug`, display
  name, macro family, taxonomy version, taxonomy status, and coverage status.
- Missing evidence is `null`, never a zero substituted for an absent
  observation.
- Every published estimate is an object with `value`, `lower`, and `upper`.
  Bounds always contain the point estimate.
- Every publishable forecast has an 80% prediction interval, genre validation,
  macro-family validation, and the naive baseline. A cold start has
  `forecast_status: "insufficient_history"` and no prediction or skill claim.
- Evidence responses expose materialized source records rather than
  recomputing receipts in the API.
- Responses carry `Cache-Control: public, max-age=60`.

## Shared values

Coverage states:

```text
ready
collecting_history
insufficient_listening
insufficient_conversation
insufficient_supply
insufficient_resolution
unsupported
not_observed
```

Taxonomy states are `enabled`, `candidate`, or `rejected`.

Cursor-paginated endpoints accept `limit` from 1 through 200 and an opaque
`cursor`. Clients must copy `page.next_cursor` exactly and must not parse or
construct it.

```json
{
  "page": {
    "next_cursor": "c291bmRjaGVjay12Mjoy",
    "has_more": true
  }
}
```

The common genre identity is:

```json
{
  "genre_id": "genre_garage_rock",
  "slug": "garage-rock",
  "display_name": "Garage Rock",
  "macro_family_id": "macro_rock",
  "macro_family_name": "Rock",
  "parent_genre_id": "genre_rock",
  "taxonomy_version": "2.0.0",
  "taxonomy_status": "enabled",
  "coverage_status": "ready"
}
```

## Taxonomy and search

### `GET /api/v2/taxonomy`

Filters: `taxonomy_version`, `macro_family_id`, `parent_genre_id`,
`eligibility_state`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "default_genre_id": "genre_indie_rock",
  "other_genre_id": "genre_other",
  "unresolved_genre_id": "genre_unresolved",
  "genres": {
    "items": [
      {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      }
    ],
    "page": {
      "next_cursor": null,
      "has_more": false
    }
  }
}
```

### `GET /api/v2/macro-families`

Filters: `taxonomy_version`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "items": [
    {
      "macro_family_id": "macro_rock",
      "display_name": "Rock",
      "slug": "rock"
    }
  ],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

### `GET /api/v2/genres/search`

Required: `q`.

Filters: `taxonomy_version`, `macro_family_id`, `parent_genre_id`,
`eligibility_state`, `limit`, and `cursor`. Search covers normalized display
names, slugs, canonical aliases, supported multilingual aliases, and source
spelling variants.

```json
{
  "items": [
    {
      "genre_id": "genre_uk_garage",
      "slug": "uk-garage",
      "display_name": "UK Garage",
      "macro_family_id": "macro_electronic",
      "macro_family_name": "Electronic",
      "parent_genre_id": "genre_electronic",
      "taxonomy_version": "2.0.0",
      "taxonomy_status": "enabled",
      "coverage_status": "collecting_history"
    }
  ],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

## Opportunity and history

### `GET /api/v2/opportunities`

Filters: `taxonomy_version`, `week`, `macro_family_id`,
`parent_genre_id`, `eligibility_state`, `context`, `limit`, and `cursor`.
The default eligibility filter is `ready`. Select another state explicitly;
use the coverage endpoint when a complete all-state inventory is required.

```json
{
  "taxonomy_version": "2.0.0",
  "week": "2026-07-20",
  "context": "peer_family",
  "items": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "week": "2026-07-20",
      "context": "peer_family",
      "estimate_status": "ready",
      "opportunity": {
        "value": 1.0,
        "lower": 0.8,
        "upper": 1.2
      },
      "discovery_gap": {
        "value": 0.2,
        "lower": 0.0,
        "upper": 0.4
      },
      "conversation": {
        "value": 1.0,
        "lower": 0.8,
        "upper": 1.2
      },
      "listening": {
        "value": 1.2,
        "lower": 1.0,
        "upper": 1.4
      },
      "supply": {
        "value": 0.7,
        "lower": 0.5,
        "upper": 0.9
      },
      "diagnostics": {
        "conversation_effective_n": 10.0,
        "listening_effective_n": 12.0,
        "supply_effective_n": 2.0,
        "conversation_shrinkage_weight": 0.72,
        "listening_shrinkage_weight": 0.0,
        "supply_shrinkage_weight": 0.48
      },
      "spike_flags": {
        "conversation": false,
        "listening": false,
        "supply": false
      },
      "breakout_flag": true
    }
  ],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

An ineligible genre remains visible when its eligibility state is requested:

```json
{
  "genre": {
    "genre_id": "genre_uk_garage",
    "slug": "uk-garage",
    "display_name": "UK Garage",
    "macro_family_id": "macro_electronic",
    "macro_family_name": "Electronic",
    "parent_genre_id": "genre_electronic",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "collecting_history"
  },
  "week": "2026-07-20",
  "context": "global",
  "estimate_status": "collecting_history",
  "opportunity": null,
  "discovery_gap": null,
  "conversation": null,
  "listening": null,
  "supply": null,
  "diagnostics": {
    "conversation_effective_n": null,
    "listening_effective_n": null,
    "supply_effective_n": null,
    "conversation_shrinkage_weight": null,
    "listening_shrinkage_weight": null,
    "supply_shrinkage_weight": null
  },
  "spike_flags": {
    "conversation": null,
    "listening": null,
    "supply": null
  },
  "breakout_flag": false
}
```

If there is no opportunity week, the endpoint returns `week: null`, empty
`items`, and a terminal page.

### `GET /api/v2/genres/{genre_id}/timeseries`

Filters: `taxonomy_version`, `context`, and `weeks`.

```json
{
  "genre": {
    "genre_id": "genre_garage_rock",
    "slug": "garage-rock",
    "display_name": "Garage Rock",
    "macro_family_id": "macro_rock",
    "macro_family_name": "Rock",
    "parent_genre_id": "genre_rock",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "ready"
  },
  "context": "global",
  "history": [
    {
      "week": "2026-07-20",
      "coverage_status": "ready",
      "estimate_status": "ready",
      "conversation": {
        "index": {"value": 1.0, "lower": 0.8, "upper": 1.2},
        "ewma": {"value": 0.95, "lower": 0.75, "upper": 1.15},
        "spike": false
      },
      "listening": {
        "index": {"value": 1.2, "lower": 1.0, "upper": 1.4},
        "ewma": {"value": 1.15, "lower": 0.95, "upper": 1.35},
        "spike": false
      },
      "supply": {
        "index": {"value": 0.7, "lower": 0.5, "upper": 0.9},
        "ewma": {"value": 0.65, "lower": 0.45, "upper": 0.85},
        "spike": false
      },
      "opportunity": {"value": 1.0, "lower": 0.8, "upper": 1.2},
      "discovery_gap": {"value": 0.2, "lower": 0.0, "upper": 0.4}
    }
  ],
  "forecasts": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "origin_week": "2026-07-20",
      "target_week": "2026-07-27",
      "context": "global",
      "target_axis": "conversation",
      "horizon": 1,
      "forecast_status": "ready",
      "model": "ets",
      "prediction_interval_80": {
        "value": 0.8,
        "lower": 0.5,
        "upper": 1.1
      },
      "genre_validation": {
        "mase": 0.7,
        "coverage_80": 0.8,
        "score_status": "scored"
      },
      "family_validation": {
        "mase": 0.8,
        "coverage_80": 0.75,
        "score_status": "scored"
      },
      "naive_baseline": {
        "prediction_interval_80": {
          "value": 0.7,
          "lower": 0.4,
          "upper": 1.0
        },
        "validation": {
          "mase": 1.0,
          "coverage_80": 0.75,
          "score_status": "scored"
        }
      },
      "valid_training_weeks": 12
    }
  ]
}
```

## Evidence

### `GET /api/v2/genres/{genre_id}/evidence`

Required: `source`, one of `conversation`, `listening`, or `supply`.

Filters: `taxonomy_version`, `week`, `limit`, and `cursor`.

A conversation receipt:

```json
{
  "genre": {
    "genre_id": "genre_garage_rock",
    "slug": "garage-rock",
    "display_name": "Garage Rock",
    "macro_family_id": "macro_rock",
    "macro_family_name": "Rock",
    "parent_genre_id": "genre_rock",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "ready"
  },
  "week": "2026-07-20",
  "source": "conversation",
  "items": [
    {
      "source": "conversation",
      "post_uri": "at://did:plc:example/app.bsky.feed.post/3example",
      "did": "did:plc:example",
      "created_at": "2026-07-21T13:20:00Z",
      "text": "Garage rock is on repeat.",
      "likes": 12,
      "reposts": 3,
      "replies": 2,
      "artist_name_raw": "Example Artist",
      "resolution_method": "direct_mbid",
      "resolution_score": 100.0,
      "join_key_type": "mbid",
      "membership_weight": 1.0,
      "membership_method": "exact_alias",
      "membership_confidence": 0.99
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

A listening receipt contains both cumulative snapshots and their validated
non-negative deltas. The API never presents the cumulative total as a weekly
signal:

```json
{
  "genre": {
    "genre_id": "genre_garage_rock",
    "slug": "garage-rock",
    "display_name": "Garage Rock",
    "macro_family_id": "macro_rock",
    "macro_family_name": "Rock",
    "parent_genre_id": "genre_rock",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "ready"
  },
  "week": "2026-07-20",
  "source": "listening",
  "items": [
    {
      "source": "listening",
      "artist_key": "mbid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "artist_name": "Example Artist",
      "artist_mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "playcount": 1100,
      "listeners": 120,
      "previous_playcount": 1000,
      "previous_listeners": 100,
      "playcount_delta": 100,
      "listeners_delta": 20,
      "fetched_at": "2026-07-27T00:05:00Z",
      "previous_fetched_at": "2026-07-20T00:05:00Z",
      "interval_days": 7.0,
      "listening_window_status": "valid_weekly",
      "membership_weight": 1.0,
      "membership_method": "exact_alias",
      "membership_confidence": 0.99
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

A supply receipt:

```json
{
  "genre": {
    "genre_id": "genre_garage_rock",
    "slug": "garage-rock",
    "display_name": "Garage Rock",
    "macro_family_id": "macro_rock",
    "macro_family_name": "Rock",
    "parent_genre_id": "genre_rock",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "ready"
  },
  "week": "2026-07-20",
  "source": "supply",
  "items": [
    {
      "source": "supply",
      "release_group_mbid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "title": "Example Record",
      "artist_credits": [
        {
          "credit_name": "Example Artist",
          "artist_name": "Example Artist",
          "mbid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          "join_phrase": ""
        }
      ],
      "first_release_date": "2026-07-22",
      "types": ["Album"],
      "genres": ["garage rock"],
      "fetched_at": "2026-07-27T00:10:00Z",
      "membership_weight": 1.0
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

## Forecasts

### `GET /api/v2/forecasts`

Filters: `taxonomy_version`, `macro_family_id`, `parent_genre_id`,
`eligibility_state`, `context`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "context": "global",
  "items": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "origin_week": "2026-07-20",
      "target_week": "2026-07-27",
      "context": "global",
      "target_axis": "listening",
      "horizon": 1,
      "forecast_status": "no_skill",
      "model": "naive",
      "prediction_interval_80": {
        "value": 1.0,
        "lower": 0.7,
        "upper": 1.3
      },
      "genre_validation": {
        "mase": 1.0,
        "coverage_80": 0.8,
        "score_status": "scored"
      },
      "family_validation": {
        "mase": 1.1,
        "coverage_80": 0.75,
        "score_status": "scored"
      },
      "naive_baseline": {
        "prediction_interval_80": {
          "value": 0.9,
          "lower": 0.6,
          "upper": 1.2
        },
        "validation": {
          "mase": 1.0,
          "coverage_80": 0.75,
          "score_status": "scored"
        }
      },
      "valid_training_weeks": 12
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

A cold start is explicit and carries no implied prediction:

```json
{
  "genre": {
    "genre_id": "genre_uk_garage",
    "slug": "uk-garage",
    "display_name": "UK Garage",
    "macro_family_id": "macro_electronic",
    "macro_family_name": "Electronic",
    "parent_genre_id": "genre_electronic",
    "taxonomy_version": "2.0.0",
    "taxonomy_status": "enabled",
    "coverage_status": "collecting_history"
  },
  "origin_week": null,
  "target_week": null,
  "context": "global",
  "target_axis": "listening",
  "horizon": 1,
  "forecast_status": "insufficient_history",
  "model": null,
  "prediction_interval_80": null,
  "genre_validation": null,
  "family_validation": null,
  "naive_baseline": null,
  "valid_training_weeks": 3
}
```

### `GET /api/v2/forecast/next-up`

Filters: `taxonomy_version`, `macro_family_id`, `parent_genre_id`,
`eligibility_state`, `context`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "context": "global",
  "items": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "origin_week": "2026-07-20",
      "target_week": "2026-07-27",
      "context": "global",
      "rank": 1,
      "predicted_opportunity": {
        "value": 1.2,
        "lower": 0.7,
        "upper": 1.6
      },
      "predicted_gain": {
        "value": 0.2,
        "lower": -0.2,
        "upper": 0.6
      },
      "conversation": {
        "model": "ets",
        "forecast_status": "ready",
        "mase": 0.7,
        "coverage_80": 0.8
      },
      "listening": {
        "model": "naive",
        "forecast_status": "no_skill",
        "mase": 1.0,
        "coverage_80": 0.75
      },
      "skill_status": "no_skill"
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

## Ecosystem health

### `GET /api/v2/ecosystem`

Filters: `taxonomy_version`, `macro_family_id`, `context`, and `weeks`.
Use `context=global` without a macro-family filter for platform-wide health.
Use `context=peer_family` with a macro family for family-local health.

```json
[
  {
    "taxonomy_version": "2.0.0",
    "week": "2026-07-20",
    "context": "peer_family",
    "macro_family_id": "macro_rock",
    "estimate_status": "ready",
    "listening_entropy": {"value": 0.6, "lower": 0.5, "upper": 0.7},
    "effective_genres": {"value": 1.8, "lower": 1.6, "upper": 2.0},
    "conversation_hhi": {"value": 0.3, "lower": 0.2, "upper": 0.4},
    "listening_top_share": {"value": 0.7, "lower": 0.6, "upper": 0.8},
    "listening_top_share_k": 2,
    "scene_churn_jaccard_4w": {
      "value": 0.5,
      "lower": 0.4,
      "upper": 0.6
    },
    "breakout_genre_ids": ["genre_garage_rock"],
    "eligible_genres": 2
  }
]
```

## Creator briefs

### `GET /api/v2/briefs`

Filters: `taxonomy_version`, `week`, `macro_family_id`,
`parent_genre_id`, `eligibility_state`, `context`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "week": "2026-07-20",
  "context": "global",
  "items": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "brief_id": "brief-garage-rock-2026-07-20",
      "week": "2026-07-20",
      "context": "global",
      "headline": "Garage rock has room to move",
      "opportunity": {"value": 1.0, "lower": 0.8, "upper": 1.2},
      "forecast_direction": {"value": 0.2, "lower": -0.2, "upper": 0.6},
      "forecast_model": "ets",
      "backtest_mase": 0.7,
      "backtest_coverage_80": 0.8,
      "rationale": "Listening change is rising ahead of release supply.",
      "recommended_actions": ["Keep the arrangement raw."],
      "evidence_uris": [
        "at://did:plc:example/app.bsky.feed.post/3example"
      ],
      "created_at": "2026-07-27T12:00:00Z"
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

Before v2 briefs have been materialized, the response is:

```json
{
  "taxonomy_version": "2.0.0",
  "week": null,
  "context": "global",
  "items": [],
  "page": {"next_cursor": null, "has_more": false}
}
```

## Scene map

### `GET /api/v2/scene-map`

Filters: `taxonomy_version`, `week`, `macro_family_id`,
`parent_genre_id`, `eligibility_state`, `context`, `limit`, and `cursor`.
Coordinates and evidence volume are materialized by the batch pipeline.

```json
{
  "taxonomy_version": "2.0.0",
  "as_of_week": "2026-07-20",
  "context": "global",
  "items": [
    {
      "genre": {
        "genre_id": "genre_garage_rock",
        "slug": "garage-rock",
        "display_name": "Garage Rock",
        "macro_family_id": "macro_rock",
        "macro_family_name": "Rock",
        "parent_genre_id": "genre_rock",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "ready"
      },
      "as_of_week": "2026-07-20",
      "context": "global",
      "x": 1.0,
      "y": 2.0,
      "opportunity": {"value": 1.0, "lower": 0.8, "upper": 1.2},
      "discovery_gap": {"value": 0.2, "lower": 0.0, "upper": 0.4},
      "evidence_volume": 3
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

## Coverage

### `GET /api/v2/coverage`

Filters: `taxonomy_version`, `week`, `macro_family_id`,
`parent_genre_id`, `eligibility_state`, `limit`, and `cursor`.

```json
{
  "taxonomy_version": "2.0.0",
  "week": "2026-07-20",
  "items": [
    {
      "genre": {
        "genre_id": "genre_uk_garage",
        "slug": "uk-garage",
        "display_name": "UK Garage",
        "macro_family_id": "macro_electronic",
        "macro_family_name": "Electronic",
        "parent_genre_id": "genre_electronic",
        "taxonomy_version": "2.0.0",
        "taxonomy_status": "enabled",
        "coverage_status": "collecting_history"
      },
      "week": "2026-07-20",
      "lastfm_tag_available": true,
      "unique_lastfm_artists": 20,
      "artists_with_consecutive_valid_snapshots": null,
      "lastfm_history_weeks": 1,
      "musicbrainz_release_group_count": 2,
      "resolved_bluesky_post_count": 8,
      "resolution_attempt_count": 10,
      "resolution_rate": 0.8,
      "cross_source_overlap_artist_count": null,
      "cross_source_overlap": null,
      "latest_source_timestamp": "2026-07-27T12:00:00Z",
      "missing_axes": ["listening"],
      "stale": false
    }
  ],
  "page": {"next_cursor": null, "has_more": false}
}
```

## Typed errors

Unknown stable genre and macro-family IDs return 404:

```json
{
  "detail": {
    "code": "unknown_genre_id",
    "message": "Unknown genre_id: genre_does_not_exist"
  }
}
```

Unsupported taxonomy versions, future weeks, non-Monday weeks, and invalid
cursors return 422:

```json
{
  "detail": {
    "code": "invalid_taxonomy_version",
    "message": "Unsupported taxonomy version: 2.9.0"
  }
}
```

```json
{
  "detail": {
    "code": "future_week",
    "message": "future ISO weeks are not available"
  }
}
```

FastAPI query-shape validation also returns the typed envelope:

```json
{
  "detail": {
    "code": "validation_error",
    "message": "Request validation failed."
  }
}
```
