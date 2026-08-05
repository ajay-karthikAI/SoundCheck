"""Fixture-only tests for taxonomy-v2 source coverage."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from soundcheck.metrics.coverage import (
    CoverageBatch,
    CoverageEvidence,
    compute_coverage,
    load_coverage_thresholds,
)
from soundcheck.metrics.coverage_storage import (
    initialize_coverage_storage,
    load_coverage_rows,
    replace_coverage_batch,
)
from soundcheck.scripts.report_coverage import (
    render_jsonlines,
    render_table,
    select_report_rows,
)
from soundcheck.taxonomy import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures"


def _batch(*, computed_at: datetime) -> CoverageBatch:
    taxonomy = load_taxonomy(FIXTURES / "taxonomy_v2.yml")
    thresholds = load_coverage_thresholds(
        FIXTURES / "coverage_thresholds.yml"
    )
    evidence = CoverageEvidence.model_validate_json(
        (FIXTURES / "coverage_evidence.json").read_text(encoding="utf-8")
    )
    return compute_coverage(
        taxonomy,
        thresholds,
        evidence,
        computed_at=computed_at,
        start_week=date(2026, 7, 6),
        end_week=date(2026, 7, 20),
    )


def test_partial_sources_history_and_missing_week_remain_explicit() -> None:
    batch = _batch(computed_at=datetime(2026, 7, 19, tzinfo=UTC))
    rows = {
        (row.genre_id, row.week_start): row
        for row in batch.rows
    }

    rock = rows[("genre_rock", date(2026, 7, 13))]
    assert rock.eligibility_state == "ready"
    assert rock.artists_with_consecutive_valid_snapshots == 1
    assert rock.musicbrainz_release_group_count == 1
    assert rock.resolved_bluesky_post_count == 1
    assert rock.resolution_rate == 1.0
    assert rock.cross_source_overlap_artist_count == 1
    assert rock.cross_source_overlap == 1.0

    collecting = rows[("genre_garage_rock", date(2026, 7, 13))]
    assert collecting.eligibility_state == "collecting_history"
    assert collecting.unique_lastfm_artists == 1
    assert collecting.artists_with_consecutive_valid_snapshots is None

    partial = rows[("genre_uk_garage", date(2026, 7, 13))]
    assert partial.eligibility_state == "insufficient_listening"
    assert partial.musicbrainz_release_group_count == 1
    assert partial.lastfm_tag_available is None
    assert partial.unique_lastfm_artists is None
    assert partial.resolved_bluesky_post_count is None

    missing_week = rows[("genre_rock", date(2026, 7, 20))]
    assert missing_week.eligibility_state == "unsupported"
    assert missing_week.lastfm_tag_available is None
    assert missing_week.unique_lastfm_artists is None
    assert missing_week.musicbrainz_release_group_count is None
    assert missing_week.resolved_bluesky_post_count is None
    assert missing_week.listening_missing is True
    assert missing_week.conversation_missing is True
    assert missing_week.supply_missing is True


def test_stale_source_evidence_is_unsupported() -> None:
    batch = _batch(computed_at=datetime(2026, 9, 1, tzinfo=UTC))
    rock = next(
        row
        for row in batch.rows
        if row.genre_id == "genre_rock"
        and row.week_start == date(2026, 7, 13)
    )
    assert rock.stale is True
    assert rock.eligibility_state == "unsupported"
    assert rock.unique_lastfm_artists == 1


def test_storage_and_both_report_formats(tmp_path: Path) -> None:
    database_path = tmp_path / "coverage.duckdb"
    batch = _batch(computed_at=datetime(2026, 7, 19, tzinfo=UTC))
    initialize_coverage_storage(database_path)
    replace_coverage_batch(database_path, batch)
    stored = load_coverage_rows(database_path, "2.0.0")
    selected = select_report_rows(stored, week=date(2026, 7, 13), all_weeks=False)

    assert len(stored) == 15
    assert len(selected) == 5
    table = render_table(selected)
    assert "GENRE COVERAGE" in table
    assert "MACRO-FAMILY SUMMARY" in table
    jsonlines = render_jsonlines(selected)
    assert '"record_type": "genre"' in jsonlines
    assert '"record_type": "macro_family"' in jsonlines
