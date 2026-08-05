"""Measured-resolution evaluation harness tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from soundcheck.scripts.eval_resolution import (
    ResolutionEvalExample,
    evaluate_examples,
    load_examples,
    main,
)


def _example(
    identifier: str,
    *,
    predicted_mbid: str | None,
    label_mbid: str | None,
    should_resolve: bool,
) -> ResolutionEvalExample:
    return ResolutionEvalExample(
        example_id=identifier,
        post_uri=f"at://post/{identifier}",
        text="fixture",
        predicted_artist_mbid=predicted_mbid,
        predicted_artist_name="Artist" if predicted_mbid else None,
        predicted_method="musicbrainz_search" if predicted_mbid else None,
        predicted_join_key_type="mbid" if predicted_mbid else None,
        label_should_resolve=should_resolve,
        label_artist_mbid=label_mbid,
        label_artist_name="Artist" if label_mbid else None,
    )


def test_unlabeled_60_row_fixture_defers_thresholds() -> None:
    examples = load_examples(Path("tests/fixtures/resolution_eval.jsonl"))

    assert len(examples) == 60
    assert len({example.post_uri for example in examples}) == 60
    assert all(example.label_should_resolve is None for example in examples)
    report = evaluate_examples(examples)
    assert report.status == "awaiting_labels"
    assert report.thresholds_enforced is False
    assert report.passed is None


def test_complete_labels_report_segments_and_pass() -> None:
    mbid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    examples = (
        _example("one", predicted_mbid=mbid, label_mbid=mbid, should_resolve=True),
        _example("two", predicted_mbid=None, label_mbid=None, should_resolve=False),
    )

    report = evaluate_examples(examples)

    assert report.status == "passed"
    assert report.thresholds_enforced is True
    assert report.passed is True
    assert report.overall is not None
    assert report.overall.precision == 1
    assert report.overall.recall == 1
    assert report.by_method["musicbrainz_search"].precision == 1
    assert report.by_join_key_type["mbid"].precision == 1


def test_complete_labels_fail_both_precision_floors() -> None:
    predicted = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    expected = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    report = evaluate_examples(
        (
            _example(
                "wrong",
                predicted_mbid=predicted,
                label_mbid=expected,
                should_resolve=True,
            ),
        )
    )

    assert report.status == "failed"
    assert report.passed is False
    assert report.overall is not None
    assert report.overall.precision == 0
    assert report.by_join_key_type["mbid"].precision == 0


def test_cli_exits_nonzero_for_complete_failing_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_path = tmp_path / "failing.jsonl"
    predicted = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    expected = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    fixture_path.write_text(
        _example(
            "wrong",
            predicted_mbid=predicted,
            label_mbid=expected,
            should_resolve=True,
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_resolution.py",
            str(fixture_path),
            "--database",
            str(tmp_path / "missing.duckdb"),
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
