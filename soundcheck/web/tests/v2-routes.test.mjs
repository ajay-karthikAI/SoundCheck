import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("all decision surfaces remain present", async () => {
  for (const route of [
    "app/page.tsx",
    "app/next-up/page.tsx",
    "app/gap/page.tsx",
    "app/genre/[slug]/page.tsx",
    "app/ecosystem/page.tsx",
    "app/briefs/page.tsx",
    "app/map/page.tsx",
    "app/methods/page.tsx",
    "app/evidence/page.tsx",
    "app/search/page.tsx",
  ]) {
    await access(new URL(route, root));
  }
});

test("taxonomy features use v2 paths and stable slug resolution", async () => {
  const api = await readFile(new URL("lib/api.ts", root), "utf8");
  const genrePage = await readFile(
    new URL("app/genre/[slug]/page.tsx", root),
    "utf8",
  );
  assert.match(api, /\/api\/v2\/taxonomy/);
  assert.match(api, /\/api\/v2\/genres\/search/);
  assert.match(api, /\/api\/v2\/opportunities/);
  assert.match(api, /\/api\/v2\/scene-map/);
  assert.match(genrePage, /resolveGenreRoute\(params\.slug\)/);
  assert.doesNotMatch(api, /\/api\/genres\/|\/api\/forecast\/next-up/);
});

test("coverage copy rejects zero-filling and explains cold starts", async () => {
  const ui = await readFile(new URL("components/ui.tsx", root), "utf8");
  const calls = await readFile(
    new URL("components/next-week-calls.tsx", root),
    "utf8",
  );
  assert.match(ui, /Insufficient history—not a zero signal/);
  assert.match(ui, /never substituted/);
  assert.match(calls, /no prediction and no skill claim/i);
  assert.match(calls, /no_skill/);
});
