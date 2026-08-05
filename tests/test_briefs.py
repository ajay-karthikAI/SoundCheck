"""Deterministic creator-brief generation from stored fixture evidence."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

from soundcheck.briefs.generate import generate_briefs
from soundcheck.briefs.models import BriefSourceBundle
from soundcheck.briefs.storage import DuckDBBriefStore

CREATED_AT = datetime(2026, 7, 20, 12, tzinfo=UTC)


def _source(fixtures_path: Path) -> BriefSourceBundle:
    return BriefSourceBundle.model_validate_json(
        (fixtures_path / "brief_generation.json").read_text(encoding="utf-8")
    )


def test_fixture_generates_deterministic_scene_aware_brief(
    fixtures_path: Path,
) -> None:
    source = _source(fixtures_path)
    first = generate_briefs(source, created_at=CREATED_AT)
    second = generate_briefs(source, created_at=CREATED_AT)

    assert first == second
    assert first.candidate_count == 1
    assert first.suppressed_effective_n == 0
    assert first.suppressed_thin_evidence == 0
    assert len(first.briefs) == 1
    brief = first.briefs[0]
    assert brief.brief_id == "2026-W29-shoegaze"
    assert "+1.12" in brief.rationale
    assert "90% CI" in brief.rationale
    assert "+0.22" in brief.rationale
    assert "80% prediction interval" in brief.rationale
    assert "Glass Harbor" in brief.rationale
    assert "Soft Static" in brief.rationale
    assert "2 release groups" in brief.rationale
    assert "typical 5.0" in brief.rationale
    assert "Dream Pop" in brief.rationale
    assert "Slowcore" in brief.rationale
    assert brief.evidence_uris[0].startswith("at://")
    assert any("last.fm" in uri for uri in brief.evidence_uris)
    assert any("musicbrainz.org" in uri for uri in brief.evidence_uris)


def test_thin_effective_sample_is_suppressed(fixtures_path: Path) -> None:
    source = _source(fixtures_path)
    thin_candidate = source.candidates[0].model_copy(
        update={"conversation_effective_n": 2.0}
    )
    thin_source = source.model_copy(update={"candidates": (thin_candidate,)})

    batch = generate_briefs(thin_source, created_at=CREATED_AT)

    assert batch.briefs == ()
    assert batch.suppressed_effective_n == 1
    assert batch.suppressed_thin_evidence == 0


def test_missing_required_receipts_is_suppressed(fixtures_path: Path) -> None:
    source = _source(fixtures_path)
    evidence = source.evidence_by_genre["shoegaze"].model_copy(
        update={"artists": source.evidence_by_genre["shoegaze"].artists[:1]}
    )
    thin_source = source.model_copy(
        update={"evidence_by_genre": {"shoegaze": evidence}}
    )

    batch = generate_briefs(thin_source, created_at=CREATED_AT)

    assert batch.briefs == ()
    assert batch.suppressed_thin_evidence == 1


def test_no_skill_forecast_is_named_in_the_brief(fixtures_path: Path) -> None:
    source = _source(fixtures_path)
    candidate = source.candidates[0].model_copy(
        update={"skill_status": "no_skill"}
    )
    no_skill_source = source.model_copy(update={"candidates": (candidate,)})

    batch = generate_briefs(no_skill_source, created_at=CREATED_AT)

    assert "naive baseline" in batch.briefs[0].rationale
    assert "no skill" in batch.briefs[0].rationale


def test_brief_source_query_handles_a_cold_database(tmp_path: Path) -> None:
    store = DuckDBBriefStore(tmp_path / "briefs.duckdb")
    asyncio.run(store.initialize())

    source = asyncio.run(store.load_sources(date(2026, 7, 13)))

    assert source.candidates == ()
    assert source.evidence_by_genre == {}
    assert source.scene_genres == ()
