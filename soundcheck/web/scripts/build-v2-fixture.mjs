import { readFile, writeFile } from "node:fs/promises";

const SOURCE = new URL("../data/demo-api.json", import.meta.url);
const OUTPUT = new URL("../data/v2-fixture-api.json", import.meta.url);
const VERSION = "2.0.0";
const WEEK = "2026-07-13";
const TARGET_WEEK = "2026-07-20";

const familySeeds = [
  ["macro_african", "African", "african", ["african music", "afrobeat", "afrobeats"]],
  ["macro_asian_regional", "Asian Regional", "asian-regional", ["asian regional music", "cantopop", "city pop"]],
  ["macro_caribbean", "Caribbean", "caribbean", ["caribbean music", "calypso", "dancehall"]],
  ["macro_classical", "Classical", "classical", ["classical", "baroque", "contemporary classical"]],
  ["macro_electronic", "Electronic", "electronic", ["electronic", "breakcore", "dubstep"]],
  ["macro_experimental_ambient", "Experimental & Ambient", "experimental-ambient", ["experimental", "ambient", "glitch"]],
  ["macro_folk_country", "Folk & Country", "folk-country", ["folk and country", "alt-country", "americana"]],
  ["macro_hip_hop", "Hip-Hop", "hip-hop", ["hip hop", "boom bap", "experimental hip hop"]],
  ["macro_jazz", "Jazz", "jazz", ["jazz", "bebop", "free jazz"]],
  ["macro_latin", "Latin", "latin", ["latin music", "bachata", "bossa nova"]],
  ["macro_metal", "Metal", "metal", ["metal", "black metal", "death metal"]],
  ["macro_pop", "Pop", "pop", ["pop", "bedroom pop", "electropop"]],
  ["macro_punk", "Punk", "punk", ["punk rock", "emo", "folk punk"]],
  ["macro_rnb_soul", "R&B & Soul", "r-and-b-soul", ["r&b", "funk", "gospel"]],
  ["macro_rock", "Rock", "rock", ["rock", "alternative rock", "indie rock"]],
];

const bands = (value, spread = 0.22) => ({
  value,
  lower: value - spread,
  upper: value + spread,
});

const slugify = (value) =>
  value
    .toLowerCase()
    .replaceAll("&", " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const idify = (value) => `genre_${slugify(value).replaceAll("-", "_")}`;

const families = familySeeds.map(([macro_family_id, display_name, slug]) => ({
  macro_family_id,
  display_name,
  slug,
}));

const genreSeeds = familySeeds.flatMap(
  ([macroFamilyId, macroFamilyName, , names]) =>
    names.map((name, index) => ({
      name,
      index,
      macroFamilyId,
      macroFamilyName,
      familyRoot: names[0],
    })),
);

function coverageFor(seed) {
  if (seed.name === "free jazz") return "insufficient_resolution";
  return seed.index === 2 ? "collecting_history" : "ready";
}

const identities = new Map(
  genreSeeds.map((seed) => {
    const identity = {
      genre_id: idify(seed.name),
      slug: slugify(seed.name),
      display_name: seed.name
        .split(" ")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ")
        .replace("R&b", "R&B"),
      macro_family_id: seed.macroFamilyId,
      macro_family_name: seed.macroFamilyName,
      parent_genre_id:
        seed.index === 0 ? null : idify(seed.familyRoot),
      taxonomy_version: VERSION,
      taxonomy_status: seed.index === 2 ? "candidate" : "enabled",
      coverage_status: coverageFor(seed),
    };
    if (seed.name === "indie rock") {
      identity.display_name = "Indie Rock";
      identity.taxonomy_status = "enabled";
      identity.coverage_status = "ready";
    }
    return [seed.name, identity];
  }),
);

const unresolvedIdentity = {
  genre_id: "genre_unresolved",
  slug: "unresolved",
  display_name: "Unresolved",
  macro_family_id: "macro_unclassified",
  macro_family_name: "Unclassified",
  parent_genre_id: null,
  taxonomy_version: VERSION,
  taxonomy_status: "enabled",
  coverage_status: "unsupported",
};

const macroFamilies = [
  ...families,
  {
    macro_family_id: "macro_unclassified",
    display_name: "Unclassified",
    slug: "unclassified",
  },
];

const input = JSON.parse(await readFile(SOURCE, "utf8"));
const latestOpenings = input.opportunities_by_week[WEEK];
const openingByGenre = new Map(
  latestOpenings.map((opening) => [opening.genre, opening]),
);
const sceneByGenre = new Map(
  input.scene_map.map((scene) => [scene.genre, scene]),
);

function mapOpportunity(seed) {
  const identity = identities.get(seed.name);
  const source = openingByGenre.get(seed.name);
  const ready = identity.coverage_status === "ready";
  return {
    genre: identity,
    week: WEEK,
    context: "global",
    estimate_status: ready ? "ready" : identity.coverage_status,
    opportunity: ready ? source.opportunity : null,
    discovery_gap: ready ? source.discovery_gap : null,
    conversation: ready ? source.z_conversation : null,
    listening: ready ? source.z_listening : null,
    supply: ready ? source.z_supply : null,
    diagnostics: {
      conversation_effective_n: ready
        ? source.effective_n.conversation
        : null,
      listening_effective_n: ready
        ? source.effective_n.conversation + 3
        : null,
      supply_effective_n: ready ? source.effective_n.supply : null,
      conversation_shrinkage_weight: ready
        ? source.shrinkage_weight.conversation
        : null,
      listening_shrinkage_weight: ready ? 0 : null,
      supply_shrinkage_weight: ready
        ? source.shrinkage_weight.supply
        : null,
    },
    spike_flags: ready
      ? source.spike_flag
      : { conversation: null, listening: null, supply: null },
    breakout_flag: ready ? source.breakout_flag : false,
  };
}

function mapForecast(identity, forecast, axis) {
  const valid = identity.coverage_status === "ready";
  if (!valid) {
    return {
      genre: identity,
      origin_week: null,
      target_week: null,
      context: "global",
      target_axis: axis,
      horizon: 1,
      forecast_status: "insufficient_history",
      model: null,
      prediction_interval_80: null,
      genre_validation: null,
      family_validation: null,
      naive_baseline: null,
      valid_training_weeks: 3,
    };
  }
  const selected =
    forecast ??
    ({
      model: "naive",
      skill_status: "no_skill",
      prediction_interval_80: bands(0, 0.7),
      backtest_mase: 1,
      backtest_coverage_80: 0.78,
    });
  const noSkill = selected.skill_status !== "skill";
  return {
    genre: identity,
    origin_week: WEEK,
    target_week: selected.target_week ?? TARGET_WEEK,
    context: "global",
    target_axis: axis,
    horizon: selected.horizon ?? 1,
    forecast_status: noSkill ? "no_skill" : "ready",
    model: noSkill ? "naive" : selected.model,
    prediction_interval_80: selected.prediction_interval_80,
    genre_validation: {
      mase: selected.backtest_mase,
      coverage_80: selected.backtest_coverage_80,
      score_status: "scored",
    },
    family_validation: {
      mase:
        selected.backtest_mase === null
          ? null
          : Math.min(1.5, selected.backtest_mase + 0.06),
      coverage_80: Math.max(
        0,
        Math.min(1, selected.backtest_coverage_80 - 0.02),
      ),
      score_status: "scored",
    },
    naive_baseline: {
      prediction_interval_80: selected.prediction_interval_80,
      validation: {
        mase: 1,
        coverage_80: 0.8,
        score_status: "scored",
      },
    },
    valid_training_weeks: 26,
  };
}

function mapHistory(seed) {
  const identity = identities.get(seed.name);
  const source = input.histories[seed.name];
  const ready = identity.coverage_status === "ready";
  return {
    genre: identity,
    context: "global",
    history: source.history.map((week) => ({
      week: week.week,
      coverage_status: identity.coverage_status,
      estimate_status: ready ? "ready" : identity.coverage_status,
      conversation: ready ? week.conversation : null,
      listening: ready ? week.listening : null,
      supply: ready ? week.supply : null,
      opportunity: ready ? week.opportunity : null,
      discovery_gap: ready ? week.discovery_gap : null,
    })),
    forecasts: [
      mapForecast(
        identity,
        source.forecasts.find((row) => row.target_axis === "conversation"),
        "conversation",
      ),
      mapForecast(
        identity,
        source.forecasts.find((row) => row.target_axis === "listening"),
        "listening",
      ),
    ],
  };
}

function mapEvidence(seed) {
  const identity = identities.get(seed.name);
  const source = input.evidence[seed.name];
  const conversation = source.bluesky_posts.map((post) => ({
    source: "conversation",
    post_uri: post.uri,
    did: post.did,
    created_at: post.created_at,
    text: post.text,
    likes: post.likes,
    reposts: post.reposts,
    replies: post.replies,
    artist_name_raw: post.artist_name_raw,
    resolution_method: post.resolution_method,
    resolution_score: post.resolution_score,
    join_key_type: post.join_key_type,
    membership_weight: 1,
    membership_method: "exact_alias",
    membership_confidence: 0.98,
  }));
  const listening =
    identity.coverage_status === "ready"
      ? source.lastfm_artists.map((artist, index) => ({
          source: "listening",
          artist_key: artist.artist_key,
          artist_name: artist.artist_name,
          artist_mbid: artist.artist_mbid,
          playcount: 100000 + artist.playcount_delta + index * 100,
          listeners: 10000 + artist.listeners_delta + index * 10,
          previous_playcount: 100000 + index * 100,
          previous_listeners: 10000 + index * 10,
          playcount_delta: artist.playcount_delta,
          listeners_delta: artist.listeners_delta,
          fetched_at: artist.fetched_at,
          previous_fetched_at: "2026-07-06T23:30:00Z",
          interval_days: 7,
          listening_window_status: "valid_weekly",
          membership_weight: 1,
          membership_method: "exact_alias",
          membership_confidence: 0.98,
        }))
      : [];
  const supply = source.musicbrainz_releases.map((release) => ({
    source: "supply",
    release_group_mbid: release.release_group_mbid,
    title: release.title,
    artist_credits: release.artist_credits,
    first_release_date: release.first_release_date,
    types: release.types,
    genres: release.genres,
    fetched_at: "2026-07-14T00:10:00Z",
    membership_weight: 1,
  }));
  const page = { next_cursor: null, has_more: false };
  return {
    conversation: {
      genre: identity,
      week: WEEK,
      source: "conversation",
      items: conversation,
      page,
    },
    listening: {
      genre: identity,
      week: WEEK,
      source: "listening",
      items: listening,
      page,
    },
    supply: {
      genre: identity,
      week: WEEK,
      source: "supply",
      items: supply,
      page,
    },
  };
}

const opportunities = genreSeeds.map(mapOpportunity);
const histories = Object.fromEntries(
  genreSeeds.map((seed) => [idify(seed.name), mapHistory(seed)]),
);
const evidence = Object.fromEntries(
  genreSeeds.map((seed) => [idify(seed.name), mapEvidence(seed)]),
);

const nextUp = input.next_up
  .map((row) => {
    const identity = identities.get(row.genre);
    if (!identity || identity.coverage_status !== "ready") return null;
    return {
      genre: identity,
      origin_week: row.origin_week,
      target_week: row.target_week,
      context: "global",
      rank: row.rank,
      predicted_opportunity: row.predicted_opportunity,
      predicted_gain: row.predicted_gain,
      conversation: {
        model: row.conversation_model.name,
        forecast_status:
          row.skill_status === "skill" ? "ready" : "no_skill",
        mase: row.conversation_model.mase,
        coverage_80: 0.8,
      },
      listening: {
        model: row.listening_model.name,
        forecast_status:
          row.skill_status === "skill" ? "ready" : "no_skill",
        mase: row.listening_model.mase,
        coverage_80: 0.78,
      },
      skill_status: row.skill_status,
    };
  })
  .filter(Boolean);

const ecosystemGlobal = input.ecosystem.map((row) => ({
  taxonomy_version: VERSION,
  week: row.week,
  context: "global",
  macro_family_id: null,
  estimate_status: "ready",
  listening_entropy: row.listening_entropy,
  effective_genres: row.effective_genres,
  conversation_hhi: row.conversation_hhi,
  listening_top_share: row.listening_top10_share,
  listening_top_share_k: 10,
  scene_churn_jaccard_4w: row.scene_churn_jaccard_4w,
  breakout_genre_ids: row.breakout_genres.map(idify),
  eligible_genres: row.opportunity_observed_genres,
}));

const ecosystemPeer = families.flatMap((family, familyIndex) =>
  ecosystemGlobal.map((row, weekIndex) => ({
    ...row,
    context: "peer_family",
    macro_family_id: family.macro_family_id,
    listening_entropy:
      row.listening_entropy &&
      bands(0.84 + familyIndex * 0.025 + weekIndex * 0.002, 0.09),
    effective_genres:
      row.effective_genres &&
      bands(2.15 + ((familyIndex + weekIndex) % 5) * 0.12, 0.18),
    conversation_hhi:
      row.conversation_hhi &&
      bands(0.31 + (familyIndex % 4) * 0.025, 0.04),
    listening_top_share:
      row.listening_top_share &&
      bands(0.62 - (familyIndex % 3) * 0.03, 0.06),
    listening_top_share_k: 2,
    eligible_genres: 2,
  })),
);

const briefs = Object.values(input.briefs_by_week)
  .flat()
  .map((brief) => {
    const identity = identities.get(brief.genre);
    if (!identity || identity.coverage_status !== "ready") return null;
    const relatedCall = input.next_up.find((row) => row.genre === brief.genre);
    return {
      genre: identity,
      brief_id: brief.brief_id,
      week: brief.week,
      context: "global",
      headline: brief.headline,
      opportunity: brief.opportunity,
      forecast_direction:
        relatedCall?.predicted_gain ?? bands(0.18, 0.48),
      forecast_model: relatedCall?.listening_model.name ?? "ets",
      backtest_mase: relatedCall?.listening_model.mase ?? 0.82,
      backtest_coverage_80: 0.79,
      rationale: brief.rationale,
      recommended_actions: brief.recommended_actions,
      evidence_uris: brief.evidence_uris,
      created_at: brief.created_at,
    };
  })
  .filter(Boolean);

const sceneMap = genreSeeds.map((seed) => {
  const identity = identities.get(seed.name);
  const source = sceneByGenre.get(seed.name);
  return {
    genre: identity,
    as_of_week: source.as_of_week,
    context: "global",
    x: source.x,
    y: source.y,
    opportunity:
      identity.coverage_status === "ready" ? source.opportunity : null,
    discovery_gap:
      identity.coverage_status === "ready" ? source.discovery_gap : null,
    evidence_volume:
      identity.coverage_status === "ready" ? source.evidence_volume : 0,
  };
});

const coverage = genreSeeds.map((seed) => {
  const identity = identities.get(seed.name);
  const receipts = input.evidence[seed.name];
  const ready = identity.coverage_status === "ready";
  const resolutionLimited =
    identity.coverage_status === "insufficient_resolution";
  return {
    genre: identity,
    week: WEEK,
    lastfm_tag_available: true,
    unique_lastfm_artists: receipts.lastfm_artists.length || 12,
    artists_with_consecutive_valid_snapshots: ready
      ? receipts.lastfm_artists.length
      : null,
    lastfm_history_weeks: ready ? 26 : 1,
    musicbrainz_release_group_count:
      receipts.musicbrainz_releases.length,
    resolved_bluesky_post_count: resolutionLimited
      ? 1
      : receipts.bluesky_posts.length,
    resolution_attempt_count: resolutionLimited
      ? 12
      : receipts.bluesky_posts.length + 1,
    resolution_rate: resolutionLimited ? 0.08 : 0.92,
    cross_source_overlap_artist_count: ready ? 3 : null,
    cross_source_overlap: ready ? 0.36 : null,
    latest_source_timestamp: "2026-07-14T00:10:00Z",
    missing_axes: ready
      ? []
      : resolutionLimited
        ? ["conversation"]
        : ["listening"],
    stale: false,
  };
});

coverage.push({
  genre: unresolvedIdentity,
  week: WEEK,
  lastfm_tag_available: null,
  unique_lastfm_artists: null,
  artists_with_consecutive_valid_snapshots: null,
  lastfm_history_weeks: null,
  musicbrainz_release_group_count: null,
  resolved_bluesky_post_count: null,
  resolution_attempt_count: null,
  resolution_rate: null,
  cross_source_overlap_artist_count: null,
  cross_source_overlap: null,
  latest_source_timestamp: null,
  missing_axes: ["conversation", "listening", "supply"],
  stale: true,
});

const payload = {
  metadata: {
    data_mode: "taxonomy_v2_fixture",
    note: "Synthetic fixture responses for local product review only.",
    default_family_id: "macro_rock",
  },
  taxonomy: {
    taxonomy_version: VERSION,
    default_genre_id: "genre_indie_rock",
    other_genre_id: "genre_other",
    unresolved_genre_id: "genre_unresolved",
    genres: {
      items: [...identities.values(), unresolvedIdentity],
      page: { next_cursor: null, has_more: false },
    },
  },
  macro_families: {
    taxonomy_version: VERSION,
    items: macroFamilies,
    page: { next_cursor: null, has_more: false },
  },
  opportunities: {
    taxonomy_version: VERSION,
    week: WEEK,
    context: "global",
    items: opportunities,
    page: { next_cursor: null, has_more: false },
  },
  histories,
  evidence,
  forecasts: {
    taxonomy_version: VERSION,
    context: "global",
    items: Object.values(histories).flatMap((history) => history.forecasts),
    page: { next_cursor: null, has_more: false },
  },
  next_up: {
    taxonomy_version: VERSION,
    context: "global",
    items: nextUp,
    page: { next_cursor: null, has_more: false },
  },
  ecosystem: [...ecosystemGlobal, ...ecosystemPeer],
  briefs: {
    taxonomy_version: VERSION,
    week: WEEK,
    context: "global",
    items: briefs,
    page: { next_cursor: null, has_more: false },
  },
  scene_map: {
    taxonomy_version: VERSION,
    as_of_week: WEEK,
    context: "global",
    items: sceneMap,
    page: { next_cursor: null, has_more: false },
  },
  coverage: {
    taxonomy_version: VERSION,
    week: WEEK,
    items: coverage,
    page: { next_cursor: null, has_more: false },
  },
};

await writeFile(OUTPUT, `${JSON.stringify(payload, null, 2)}\n`);
console.log(`wrote ${OUTPUT.pathname}`);
