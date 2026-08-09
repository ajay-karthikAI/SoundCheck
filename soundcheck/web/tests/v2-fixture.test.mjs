import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const fixture = JSON.parse(
  await readFile(
    new URL("../data/v2-fixture-api.json", import.meta.url),
    "utf8",
  ),
);

function assertBand(band, label) {
  assert.equal(typeof band.value, "number", `${label} point`);
  assert.ok(band.lower <= band.value, `${label} lower contains point`);
  assert.ok(band.value <= band.upper, `${label} upper contains point`);
}

test("taxonomy v2 carries stable identity and an indie-focused default", () => {
  assert.equal(fixture.taxonomy.taxonomy_version, "2.0.0");
  assert.equal(fixture.metadata.default_family_id, "macro_rock");
  assert.ok(fixture.macro_families.items.length >= 15);
  for (const genre of fixture.taxonomy.genres.items) {
    assert.ok(genre.genre_id);
    assert.ok(genre.slug);
    assert.ok(genre.display_name);
    assert.ok(genre.macro_family_id);
    assert.equal(genre.taxonomy_version, "2.0.0");
    assert.ok(genre.coverage_status);
  }
});

test("published opportunity estimates always carry containing intervals", () => {
  for (const item of fixture.opportunities.items) {
    for (const field of [
      "opportunity",
      "discovery_gap",
      "conversation",
      "listening",
      "supply",
    ]) {
      if (item[field] !== null) assertBand(item[field], field);
    }
    if (item.genre.coverage_status !== "ready") {
      assert.equal(item.opportunity, null);
    }
  }
});

test("unsupported and partial genres are not rendered as zero activity", () => {
  const partial = fixture.coverage.items.filter(
    (item) => item.genre.coverage_status !== "ready",
  );
  assert.ok(partial.length > 0);
  for (const coverage of partial) {
    const opportunity = fixture.opportunities.items.find(
      (item) => item.genre.genre_id === coverage.genre.genre_id,
    );
    if (opportunity) assert.equal(opportunity.opportunity, null);
    assert.ok(
      coverage.missing_axes.length > 0 ||
        coverage.genre.coverage_status === "collecting_history",
    );
  }
});

test("cold starts make no prediction or skill claim", () => {
  const coldStarts = fixture.forecasts.items.filter(
    (forecast) => forecast.forecast_status === "insufficient_history",
  );
  assert.ok(coldStarts.length > 0);
  for (const forecast of coldStarts) {
    assert.ok(forecast.valid_training_weeks < 8);
    assert.equal(forecast.prediction_interval_80, null);
    assert.equal(forecast.model, null);
  }
});

test("publishable forecasts show interval, validation, and naive baseline", () => {
  const published = fixture.forecasts.items.filter(
    (forecast) => forecast.prediction_interval_80 !== null,
  );
  assert.ok(published.length > 0);
  for (const forecast of published) {
    assertBand(forecast.prediction_interval_80, "forecast");
    assert.ok(forecast.genre_validation);
    assert.ok(forecast.family_validation);
    assert.ok(forecast.naive_baseline);
    assertBand(
      forecast.naive_baseline.prediction_interval_80,
      "naive baseline",
    );
  }
});

test("Last.fm receipts are consecutive nonnegative snapshot deltas", () => {
  let observed = 0;
  for (const sources of Object.values(fixture.evidence)) {
    for (const item of sources.listening?.items ?? []) {
      observed += 1;
      assert.equal(
        item.playcount_delta,
        item.playcount - item.previous_playcount,
      );
      assert.equal(
        item.listeners_delta,
        item.listeners - item.previous_listeners,
      );
      assert.ok(item.playcount_delta >= 0);
      assert.ok(item.listeners_delta >= 0);
      assert.ok(item.previous_fetched_at < item.fetched_at);
      assert.equal(item.interval_days, 7);
      assert.equal(item.listening_window_status, "valid_weekly");
    }
  }
  assert.ok(observed > 0);
});
