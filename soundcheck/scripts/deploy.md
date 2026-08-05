# Soundcheck production deployment

Soundcheck publishes the immutable weekly DuckDB artifact inside a read-only
FastAPI function on Vercel. The web application is hosted by OpenAI Sites at:

```text
https://soundcheck-indie.ajayk19989.chatgpt.site
```

The frontend reads only the frozen HTTP contract. It never receives or opens
the DuckDB file. The current Sites access policy is owner-only; hosting a URL
does not by itself make the application public.

## 1. Create the Vercel API project

Use a personal Vercel Hobby account; no paid plan is required for this
project's current artifact size. Install and authenticate the pinned CLI:

```bash
npm install --global vercel@56.5.0
vercel login
```

Create the minimal deployment bundle from the repository root:

```bash
uv run python -m soundcheck.scripts.prepare_vercel_api
cd .vercel-api
vercel link
```

Choose the personal Hobby scope and name the project `soundcheck-api`. The
bundle contains only FastAPI, Pydantic, DuckDB, the read queries, and the
current `data/soundcheck.duckdb`. It deliberately excludes the batch,
embedding, and forecasting dependencies.

Deploy the first immutable snapshot:

```bash
vercel deploy --prod
cd ..
```

Record the stable production origin printed by Vercel, without a trailing
slash. Verify that it serves the baked artifact in read-only mode:

```bash
curl --fail --silent --show-error \
  https://YOUR-API-DOMAIN.vercel.app/api/health
```

FastAPI entry-point discovery and Python runtime behavior are documented by
Vercel:
[FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi) and
[Python runtime](https://vercel.com/docs/functions/runtimes/python).

## 2. Connect the Sites frontend

Set this non-secret production runtime variable on the existing Sites project:

```text
SOUNDCHECK_API_URL=https://YOUR-API-DOMAIN.vercel.app
```

Leave `SOUNDCHECK_DATA_MODE` unset in production. The value
`synthetic_demo` is reserved for explicit local demonstrations; production
must show real API data, an honest cold-start state, or a typed API error.

Save and deploy a new Sites version after changing environment variables. Keep
the existing owner-only access policy unless the owner explicitly changes it.
The API CORS allowlist already includes the exact Sites origin.

## 3. Create the CI deployment identity

After `vercel link`, read `.vercel-api/.vercel/project.json`. Create a Vercel
access token, then add the following repository secrets under
**GitHub → Settings → Secrets and variables → Actions**:

| Secret | Value |
| --- | --- |
| `LASTFM_API_KEY` | Free Last.fm API key |
| `MUSICBRAINZ_CONTACT_EMAIL` | Public operations contact used in the User-Agent |
| `VERCEL_TOKEN` | Vercel access token |
| `VERCEL_ORG_ID` | `orgId` from `.vercel-api/.vercel/project.json` |
| `VERCEL_API_PROJECT_ID` | `projectId` from `.vercel-api/.vercel/project.json` |
| `SOUNDCHECK_API_URL` | Stable production Vercel API origin, no trailing slash |

The workflow passes secrets only through environment variables. It never logs
the Last.fm key or the MusicBrainz contact.

## 4. Enable and verify automation

Push the default branch and run
**Actions → Soundcheck data pipeline → Run workflow → weekly** once.
Scheduled workflows run from the default branch in UTC. Collectors run at
05:17 UTC Tuesday through Sunday; the complete weekly pipeline runs Monday at
06:47 UTC.

Each successful run restores the latest database artifact, collects the three
public sources, and runs:

```text
ingest
→ resolve v1 and v2
→ metrics v1 and v2
→ forecast v1 and v2
→ briefs
→ publish DuckDB and taxonomy-comparison artifact
→ deploy Vercel API
```

The Vercel deployment is atomic: a failed pipeline leaves the previous
production function and database snapshot in place. The stable Sites
application fetches the newly deployed API within its 60-second cache window,
so a weekly frontend redeploy is unnecessary.

The first Last.fm snapshot correctly produces no listening metric. A valid
listening delta requires consecutive append-only snapshots spanning ISO weeks;
forecast validation needs at least eight training weeks. Do not bypass either
cold-start state.

Final checks:

```bash
curl --fail --silent --show-error \
  https://YOUR-API-DOMAIN.vercel.app/api/health
open https://soundcheck-indie.ajayk19989.chatgpt.site/evidence
```

The health response must report `datastore_mode: "read_only"`. The evidence
page must show public source receipts rather than synthetic demo records.

## 5. Taxonomy-v2 cutover

The weekly workflow computes v1 and v2 together, but it does not switch the
Sites frontend. First run:

```bash
make compare-taxonomies
uv run python scripts/compare_taxonomy_versions.py --require-cutover
```

The second command must exit successfully. Its JSON counterpart must be stored
beside the exact DuckDB artifact being deployed. The required resolution,
coverage, history, missingness, forecast, runtime, recovery, and freshness
checks are defined in
[taxonomy-v2 cutover](../docs/taxonomy_v2_cutover.md).

For an explicit CI cutover check, manually dispatch the weekly workflow with
`cutover_taxonomy_v2` selected. The workflow stops before deployment when any
gate fails. It still uploads the immutable failure artifact and comparison
report so the attempt is recoverable and auditable.

If the report passes, record:

- the current and candidate Sites version IDs;
- the Vercel production deployment ID;
- the workflow run and artifact name; and
- the comparison report's taxonomy version and generation timestamp.

Verify production health, v2 coverage, direct evidence receipts, uncertainty
bands, `no_skill` states, and freshness before deploying the saved v2 Sites
version. Preserve the v1 API routes throughout.

## 6. Recovery and rollback

Collector checkpoints are deterministic by pinned collection date, phase, and
shard. A rerun first restores the current workflow run's latest immutable
artifact; otherwise it restores the latest successful run. The artifact
contains `data/soundcheck.duckdb` and, for weekly runs, the taxonomy comparison
JSON. Raw snapshots remain append-only, v2 writes remain version-scoped, and
stable MusicBrainz rows remain insert-on-first-sight.

To roll back a cutover:

1. Redeploy the recorded previous Sites version.
2. Promote the recorded previous Vercel production deployment.
3. If needed, restore the recorded previous workflow artifact and rebuild the
   immutable API bundle from it.
4. Verify the v1 health, evidence, uncertainty, forecast skill, and freshness
   endpoints.
5. Leave the failed v2 families candidate or disabled and retain their
   versioned tables for diagnosis.

Do not delete v2 tables, edit v1 historical rows, or rewrite raw observations
during rollback.
