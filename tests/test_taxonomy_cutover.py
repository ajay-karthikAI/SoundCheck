"""Fail-closed taxonomy-v2 comparison and migration tests."""

from __future__ import annotations

from pathlib import Path

from soundcheck.scripts.compare_taxonomy_versions import (
    _mapping_comparison,
    _valid_forecast_row,
    load_cutover_config,
)
from soundcheck.taxonomy import load_taxonomy


def test_mapping_comparison_keeps_unresolved_distinct_from_other() -> None:
    taxonomy = load_taxonomy()
    v1_rows: tuple[tuple[object, ...], ...] = (
        ("lastfm", "indie rock", "indie rock", "exact", 1.0),
        ("lastfm", "space banjo", "other", "below_floor", 0.2),
    )
    v2_rows: tuple[tuple[object, ...], ...] = (
        (
            "lastfm",
            "indie rock",
            "indie rock",
            "genre_indie_rock",
            "macro_rock",
            "exact_alias",
            1.0,
            1.0,
        ),
        (
            "lastfm",
            "space banjo",
            "space banjo",
            taxonomy.unresolved_genre_id,
            "macro_unclassified",
            "below_floor",
            0.2,
            1.0,
        ),
    )

    changes, unresolved = _mapping_comparison(v1_rows, v2_rows, taxonomy)

    assert len(changes) == 1
    assert changes[0].source_tag == "space banjo"
    assert changes[0].v2_unresolved
    assert unresolved.v1_other_tags == 1
    assert unresolved.v2_unresolved_tags == 1


def test_cutover_forecast_requires_intervals_validation_and_naive_receipt() -> None:
    config = load_cutover_config().forecast
    valid: tuple[object, ...] = (
        "genre_indie_rock",
        "macro_rock",
        "global",
        "conversation",
        1,
        "no_skill",
        "naive",
        0.2,
        -0.1,
        0.5,
        1.0,
        0.8,
        1.0,
        0.8,
        0.2,
        -0.1,
        0.5,
        12,
        None,
    )

    assert _valid_forecast_row(valid, config)
    assert not _valid_forecast_row(
        (*valid[:11], 0.59, *valid[12:]),
        config,
    )
    assert not _valid_forecast_row(
        (*valid[:14], None, None, None, *valid[17:]),
        config,
    )
    assert not _valid_forecast_row(
        (*valid[:5], "insufficient_history", *valid[6:]),
        config,
    )


def test_weekly_workflow_dual_runs_then_artifacts_then_deploys() -> None:
    workflow = Path(".github/workflows/weekly.yml").read_text(encoding="utf-8")
    ordered_markers = (
        "Collect public Bluesky conversation",
        "Collect Last.fm listening snapshots",
        "Collect MusicBrainz release supply",
        "Resolve artists and canonical genres",
        "Resolve taxonomy-v2 genre memberships",
        "Compute weekly metrics",
        "Compute taxonomy-v2 weekly metrics",
        "Backtest and publish forecasts",
        "Backtest and publish taxonomy-v2 forecasts",
        "Generate evidence-linked creator briefs",
        "Upload immutable database artifact",
        "Deploy the API artifact to Vercel",
    )
    positions = tuple(workflow.index(marker) for marker in ordered_markers)

    assert positions == tuple(sorted(positions))
    assert "Compare taxonomy versions and enforce an explicit cutover" in workflow
    assert "TAXONOMY_V2_CUTOVER_REQUESTED" in workflow
    assert "artifacts/taxonomy-v2-comparison.json" in workflow
