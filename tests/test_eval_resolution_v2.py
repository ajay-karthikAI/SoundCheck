"""Stratified taxonomy-v2 evaluation and activation tests."""

from __future__ import annotations

from pathlib import Path

import duckdb

from soundcheck.resolve.genres_v2 import load_resolution_v2_config
from soundcheck.scripts.eval_resolution_v2 import (
    ResolutionV2EvalExample,
    evaluate_examples,
    persist_family_activation,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import load_taxonomy

_TAXONOMY_PATH = Path("tests/fixtures/taxonomy_v2.yml")


def _example(
    index: int,
    *,
    macro_family_id: str = "macro_rock",
    predicted: tuple[str, ...] = ("genre_rock",),
    label: tuple[str, ...] | None = None,
    language: str = "und",
    method: str = "exact_alias",
    join_key_type: str = "mbid",
) -> ResolutionV2EvalExample:
    payload = {
        "example_id": f"example-{index:03d}",
        "artist_key": f"mbid:{index:032d}",
        "artist_name": f"Artist {index}",
        "source_system": "lastfm",
        "source_tag": "rock",
        "predicted_genre_ids": predicted,
        "predicted_method": method,
        "macro_family_id": macro_family_id,
        "language": language,
        "join_key_type": join_key_type,
        "popularity_tier": ("low", "mid", "high")[index % 3],
        "label_should_resolve": None if label is None else bool(label),
        "label_genre_ids": () if label is None else label,
    }
    return ResolutionV2EvalExample.model_validate(payload)


def test_blank_labels_are_not_invented_or_activated() -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()
    examples = tuple(_example(index) for index in range(320))

    report = evaluate_examples(examples, taxonomy, config.activation)

    assert report.status == "awaiting_labels"
    assert report.total_examples == 320
    assert report.labeled_examples == 0
    assert report.overall is None
    assert all(
        not decision.production_eligible
        and decision.status == "candidate"
        and "insufficient_labeled_examples" in decision.reasons
        for decision in report.family_activation.values()
    )


def test_metrics_are_stratified_and_quality_controls_activation() -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()
    correct = tuple(
        _example(
            index,
            label=("genre_rock",),
            language="es" if index % 2 else "und",
            method=(
                "exact_multilingual_alias"
                if index % 2
                else "exact_alias"
            ),
        )
        for index in range(20)
    )

    report = evaluate_examples(correct, taxonomy, config.activation)

    assert report.overall is not None
    assert report.overall.precision == 1.0
    assert report.overall.recall == 1.0
    assert set(report.by_language) == {"es", "und"}
    assert set(report.by_method) == {
        "exact_alias",
        "exact_multilingual_alias",
    }
    assert report.by_join_key_type["mbid"].precision == 1.0
    assert report.family_activation["macro_rock"].production_eligible
    assert not report.family_activation["macro_electronic"].production_eligible

    wrong = (
        *correct[:14],
        *(
            _example(
                100 + index,
                predicted=("genre_garage_rock",),
                label=("genre_rock",),
            )
            for index in range(6)
        ),
    )
    failed = evaluate_examples(wrong, taxonomy, config.activation)
    decision = failed.family_activation["macro_rock"]
    assert not decision.production_eligible
    assert decision.status == "candidate"
    assert "precision_below_threshold" in decision.reasons
    assert "recall_below_threshold" in decision.reasons


def test_activation_state_is_written_only_to_v2_staging(tmp_path: Path) -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()
    report = evaluate_examples(
        tuple(
            _example(index, label=("genre_rock",))
            for index in range(20)
        ),
        taxonomy,
        config.activation,
    )
    database_path = tmp_path / "activation.duckdb"

    persist_family_activation(database_path, report, taxonomy)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_stg_genre_family_activation_v2.sql"),
            [taxonomy.taxonomy_version],
        ).fetchall()
    assert len(rows) == len(taxonomy.macro_families)
    rock = next(row for row in rows if row[0] == "macro_rock")
    unclassified = next(
        row for row in rows if row[0] == "macro_unclassified"
    )
    assert rock[1:3] == ("active", True)
    assert unclassified[1:3] == ("candidate", False)
    assert "unclassified_family_not_activatable" in unclassified[7]
