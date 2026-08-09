ifneq (,$(wildcard .env))
include .env
export LASTFM_API_KEY
endif

.PHONY: lint typecheck test ingest-bluesky poll-bluesky-engagement recover-bluesky-engagement plan-collection plan-promotion ingest-lastfm ingest-lastfm-shard finalize-lastfm ingest-musicbrainz ingest-musicbrainz-shard finalize-musicbrainz backfill-musicbrainz resolve resolve-v2 eval-resolution-v2 generate-resolution-v2-eval coverage report-coverage metrics metrics-v2 forecast forecast-v2 compare-taxonomies briefs api demo-data demo-api

lint:
	uv run ruff check .

typecheck:
	uv run mypy

test:
	uv run pytest

ingest-bluesky:
	uv run python -m soundcheck.ingest.bluesky.jetstream

poll-bluesky-engagement:
	uv run python -m soundcheck.ingest.bluesky.appview --due

recover-bluesky-engagement:
	uv run python -m soundcheck.ingest.bluesky.appview --overdue

plan-collection:
	uv run python -m soundcheck.scripts.plan_collection

plan-promotion:
	uv run python -m soundcheck.scripts.plan_promotion

ingest-lastfm:
	uv run python -m soundcheck.ingest.lastfm.collect

ingest-lastfm-shard:
	uv run python -m soundcheck.ingest.lastfm.collect --run-key "$(RUN_KEY)" --phase "$(PHASE)" --shard-count "$(SHARD_COUNT)" --shard-index "$(SHARD_INDEX)"

finalize-lastfm:
	uv run python -m soundcheck.ingest.lastfm.collect --run-key "$(RUN_KEY)" --phase finalize --shard-count "$(SHARD_COUNT)"

ingest-musicbrainz:
	uv run python -m soundcheck.ingest.musicbrainz.collect incremental

ingest-musicbrainz-shard:
	uv run python -m soundcheck.ingest.musicbrainz.collect --run-key "$(RUN_KEY)" --phase collect --shard-count "$(SHARD_COUNT)" --shard-index "$(SHARD_INDEX)" incremental --as-of "$(AS_OF)"

finalize-musicbrainz:
	uv run python -m soundcheck.ingest.musicbrainz.collect --run-key "$(RUN_KEY)" --phase finalize --shard-count "$(SHARD_COUNT)" incremental --as-of "$(AS_OF)"

backfill-musicbrainz:
	uv run python -m soundcheck.ingest.musicbrainz.collect backfill --start "$(START)" --end "$(END)"

resolve:
	uv run python -m soundcheck.resolve.run

resolve-v2:
	uv run python -m soundcheck.resolve.run_v2

eval-resolution-v2:
	uv run python -m soundcheck.scripts.eval_resolution_v2

generate-resolution-v2-eval:
	uv run python -m soundcheck.scripts.generate_resolution_v2_eval

coverage:
	uv run python -m soundcheck.metrics.coverage_run

report-coverage:
	uv run python scripts/report_coverage.py

metrics:
	uv run python -m soundcheck.metrics.run

metrics-v2:
	uv run python -m soundcheck.metrics.v2_run

forecast:
	uv run python -m soundcheck.forecast.run

forecast-v2:
	uv run python -m soundcheck.forecast.v2_run

compare-taxonomies:
	uv run python scripts/compare_taxonomy_versions.py

briefs:
	uv run python -m soundcheck.briefs.generate

api:
	uv run uvicorn soundcheck.api.app:app --host 0.0.0.0 --port 8000

demo-data:
	uv run python -m soundcheck.scripts.seed_demo
	uv run python -m soundcheck.scripts.export_demo_web

demo-api:
	SOUNDCHECK_DB_PATH=data/soundcheck-demo.duckdb uv run uvicorn soundcheck.api.app:app --host 0.0.0.0 --port 8000
