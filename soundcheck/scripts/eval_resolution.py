"""Report labeled entity-resolution precision and recall; enforce quality floors."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict, field_validator

from soundcheck.sql.loader import load_sql

DEFAULT_EVAL_PATH = Path("tests/fixtures/resolution_eval.jsonl")
DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
MBID_PRECISION_FLOOR = 0.98
OVERALL_PRECISION_FLOOR = 0.85


def _blank_to_none(value: object) -> object:
    return None if value == "" else value


class ResolutionEvalExample(BaseModel):
    """One prediction and its initially blank human label."""

    model_config = ConfigDict(frozen=True)

    example_id: str
    post_uri: str
    text: str
    link_urls: tuple[str, ...] = ()
    predicted_artist_mbid: str | None = None
    predicted_artist_name: str | None = None
    predicted_method: str | None = None
    predicted_join_key_type: str | None = None
    label_should_resolve: bool | None = None
    label_artist_mbid: str | None = None
    label_artist_name: str | None = None

    _normalize_blank_strings = field_validator(
        "predicted_artist_mbid",
        "predicted_artist_name",
        "predicted_method",
        "predicted_join_key_type",
        "label_artist_mbid",
        "label_artist_name",
        mode="before",
    )(_blank_to_none)


class ResolutionMetrics(BaseModel):
    """Binary-link precision and recall counts."""

    model_config = ConfigDict(frozen=True)

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float


class ResolutionEvalReport(BaseModel):
    """Overall and segmented quality report."""

    model_config = ConfigDict(frozen=True)

    status: str
    total_examples: int
    labeled_examples: int
    overall: ResolutionMetrics | None
    by_method: dict[str, ResolutionMetrics]
    by_join_key_type: dict[str, ResolutionMetrics]
    thresholds_enforced: bool
    passed: bool | None


def load_examples(path: Path) -> tuple[ResolutionEvalExample, ...]:
    """Load a JSON Lines evaluation fixture."""
    examples: list[ResolutionEvalExample] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            examples.append(ResolutionEvalExample.model_validate_json(line))
        except ValueError as exc:
            msg = f"invalid evaluation row at line {line_number}"
            raise ValueError(msg) from exc
    return tuple(examples)


def attach_current_predictions(
    examples: Sequence[ResolutionEvalExample],
    database_path: Path,
) -> tuple[ResolutionEvalExample, ...]:
    """Attach current preferred staged links without changing human labels."""
    if not database_path.exists():
        return tuple(examples)
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_preferred_stg_post_artist_links.sql")
            ).fetchall()
    except duckdb.CatalogException:
        return tuple(examples)
    prediction_by_uri = {
        row[0]: {
            "predicted_artist_mbid": row[1],
            "predicted_artist_name": row[2],
            "predicted_method": row[3],
            "predicted_join_key_type": row[4],
        }
        for row in rows
    }
    return tuple(
        example.model_copy(update=prediction_by_uri.get(example.post_uri, {}))
        for example in examples
    )


def evaluate_examples(
    examples: Sequence[ResolutionEvalExample],
) -> ResolutionEvalReport:
    """Calculate metrics and enforce floors only after every row is labeled."""
    labeled = tuple(
        example for example in examples if example.label_should_resolve is not None
    )
    if not labeled:
        return ResolutionEvalReport(
            status="awaiting_labels",
            total_examples=len(examples),
            labeled_examples=0,
            overall=None,
            by_method={},
            by_join_key_type={},
            thresholds_enforced=False,
            passed=None,
        )

    overall = _metrics(labeled)
    by_method = _grouped_metrics(
        labeled,
        lambda example: example.predicted_method or "unresolved",
    )
    by_join_key = _grouped_metrics(
        labeled,
        lambda example: example.predicted_join_key_type or "unresolved",
    )
    complete = len(labeled) == len(examples)
    mbid_precision = by_join_key.get(
        "mbid",
        ResolutionMetrics(
            true_positives=0,
            false_positives=0,
            false_negatives=0,
            precision=0.0,
            recall=0.0,
        ),
    ).precision
    passed = (
        mbid_precision >= MBID_PRECISION_FLOOR
        and overall.precision >= OVERALL_PRECISION_FLOOR
    )
    return ResolutionEvalReport(
        status="passed" if complete and passed else "failed" if complete else "partially_labeled",
        total_examples=len(examples),
        labeled_examples=len(labeled),
        overall=overall,
        by_method=by_method,
        by_join_key_type=by_join_key,
        thresholds_enforced=complete,
        passed=passed if complete else None,
    )


def _grouped_metrics(
    examples: Sequence[ResolutionEvalExample],
    key: Callable[[ResolutionEvalExample], str],
) -> dict[str, ResolutionMetrics]:
    groups: dict[str, list[ResolutionEvalExample]] = defaultdict(list)
    for example in examples:
        groups[key(example)].append(example)
    return {
        name: _metrics(group)
        for name, group in sorted(groups.items())
    }


def _metrics(examples: Sequence[ResolutionEvalExample]) -> ResolutionMetrics:
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    for example in examples:
        expected = example.label_should_resolve is True
        predicted = _has_prediction(example)
        correct = expected and predicted and _identity_matches(example)
        if correct:
            true_positives += 1
        elif predicted:
            false_positives += 1
        if expected and not correct:
            false_negatives += 1
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    return ResolutionMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=(
            true_positives / precision_denominator
            if precision_denominator
            else 0.0
        ),
        recall=(
            true_positives / recall_denominator
            if recall_denominator
            else 0.0
        ),
    )


def _has_prediction(example: ResolutionEvalExample) -> bool:
    return (
        example.predicted_artist_mbid is not None
        or example.predicted_artist_name is not None
    )


def _identity_matches(example: ResolutionEvalExample) -> bool:
    if example.label_artist_mbid is not None:
        return (
            example.predicted_artist_mbid is not None
            and example.predicted_artist_mbid.casefold()
            == example.label_artist_mbid.casefold()
        )
    if example.label_artist_name is not None:
        return (
            example.predicted_artist_name is not None
            and example.predicted_artist_name.strip().casefold()
            == example.label_artist_name.strip().casefold()
        )
    return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, nargs="?", default=DEFAULT_EVAL_PATH)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    examples = attach_current_predictions(
        load_examples(args.fixture),
        args.database,
    )
    report = evaluate_examples(examples)
    print(
        json.dumps(
            report.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    if report.thresholds_enforced and report.passed is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
