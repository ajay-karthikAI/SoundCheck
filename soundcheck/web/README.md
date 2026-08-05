# Soundcheck web

The frontend is a strict Next.js 14 App Router application that consumes only
the frozen API contracts in `../docs/api_contract.md` and
`../docs/api_contract_v2.md`. Taxonomy-v2 product features call only
`/api/v2`; the original contract and familiar `/genre/<slug>` links remain
valid.

The default view is the Rock macro family with peer-family comparisons—the
indie-focused lens. Choose **All music** or another macro family in the header
to move across the enabled taxonomy without losing the evidence and
uncertainty rules.

## Run locally

Start the API from the repository root:

```bash
make api
```

In a second terminal:

```bash
cd soundcheck/web
npm install
npm run dev
```

Open `http://localhost:3000`.

Development uses `.next-dev/`, while production builds use `.next/`. This
keeps `npm run build` from invalidating the CSS and JavaScript assets of a
running development server.

## Review taxonomy v2 with fixture responses

Phase I is fixture-first and does not switch the production site. The checked-in
v2 fixture covers all macro families, ready and partial coverage, cold-start
forecasts, public-source-shaped evidence receipts, uncertainty intervals, and
model validation.

```bash
cd soundcheck/web
npm run fixtures
SOUNDCHECK_DATA_MODE=taxonomy_v2_fixture npm run dev
```

Open `http://localhost:3000`. A persistent banner identifies fixture data so it
cannot be mistaken for observed evidence. Useful reviewer paths:

- `/` — indie-focused Rock family, peer comparison;
- `/?family=macro_electronic&context=peer_family` — another family;
- `/?family=all&context=global` — all eligible music;
- `/next-up` — validated calls and cold-start states;
- `/gap`, `/ecosystem`, `/briefs`, `/map`, and `/evidence`;
- `/search?q=shoegaze`;
- `/genre/indie-rock` — stable slug resolution and receipts.

## Run the legacy synthetic DuckDB demo

The demo generator creates `data/soundcheck-demo.duckdb` and refuses to
overwrite the real `data/soundcheck.duckdb`. It contains 26 completed ISO weeks
across a balanced 45-genre taxonomy-v2 sample: three genres from each of 15
music macro families, mixing enabled and candidate definitions where
available. Rejected, `other`, and `unresolved` definitions are excluded. The
artifact includes evidence receipts for all three axes, forecasts with
backtest scores, ecosystem health, scene-map points, and creator briefs. Every
page displays a persistent synthetic-data banner. Candidate rows are product
evaluation data only and do not enable those genres in the observed pipeline.

Stop any API already using port 8000, then run from the repository root:

```bash
make demo-data
make demo-api
```

`make demo-data` also refreshes `soundcheck/web/data/demo-api.json`, the static
synthetic payload used when a Python API is unavailable.

In a second terminal:

```bash
cd soundcheck/web
npm run dev
```

Open `http://localhost:3000` and use every navigation tab. Return to observed
data by stopping the demo API and running `make api`. Regenerating the demo
database replaces only the disposable demo artifact.

To run solely from the generated static payload, without `make demo-api`:

```bash
cd soundcheck/web
SOUNDCHECK_DATA_MODE=synthetic_demo npm run dev
```

The server-side API client defaults to `http://127.0.0.1:8000`. Override it
without exposing the value to browser JavaScript:

```bash
SOUNDCHECK_API_URL=https://api.example.com npm run dev
```

Set `SOUNDCHECK_WEB_URL` to the public site origin in production so Open Graph
image URLs resolve correctly.

## Validate

```bash
npm run fixtures
npm run typecheck
npm run lint
npm test
npm run build
```

The fixture tests enforce interval containment, explicit non-ready states,
nonnegative Last.fm snapshot deltas, forecast validation, and taxonomy identity
fields. No frontend test makes a live network request.
