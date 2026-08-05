"""Evaluate taxonomy-v2 genre memberships and report activation eligibility."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from soundcheck.resolve.genres_v2 import (
    DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    ActivationThresholds,
    load_resolution_v2_config,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, GenreTaxonomy, load_taxonomy

DEFAULT_EVAL_V2_PATH = Path("tests/fixtures/resolution_v2_eval.jsonl")
DEFAULT_DATABASE_PATH = Path("data/soundcheck.duckdb")
JoinKeyType = Literal["mbid", "name", "unknown"]
PopularityTier = Literal["low", "mid", "high", "unknown"]


def _blank_to_none(value: object) -> object:
    return None if value == "" else value


class ResolutionV2EvalExample(BaseModel):
    """One membership prediction with intentionally human-only labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str
    artist_key: str
    artist_name: str
    source_system: str
    source_tag: str
    predicted_genre_ids: tuple[str, ...]
    predicted_method: str
    macro_family_id: str
    language: str
    join_key_type: JoinKeyType
    popularity_tier: PopularityTier
    label_should_resolve: bool | None = None
    label_genre_ids: tuple[str, ...] = ()

    _normalize_blank_label = field_validator(
        "label_should_resolve",
        mode="before",
    )(_blank_to_none)

    @field_validator("predicted_genre_ids", "label_genre_ids")
    @classmethod
    def normalize_genre_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values if value.strip())
        if len(set(normalized)) != len(normalized):
            raise ValueError("genre ID sets cannot contain duplicates")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_human_label(self) -> ResolutionV2EvalExample:
        if self.label_should_resolve is True and not self.label_genre_ids:
            raise ValueError("positive human labels require label_genre_ids")
        if self.label_should_resolve is False and self.label_genre_ids:
            raise ValueError("negative human labels cannot include genre IDs")
        if self.label_should_resolve is None and self.label_genre_ids:
            raise ValueError("blank human labels cannot include genre IDs")
        return self


class MembershipMetrics(BaseModel):
    """Set-membership precision and recall counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    labeled_examples: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float


class FamilyActivation(BaseModel):
    """Whether one macro family has enough measured quality for production."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    macro_family_id: str
    status: Literal["active", "candidate"]
    production_eligible: bool
    labeled_examples: int
    precision: float | None
    recall: float | None
    mbid_precision: float | None
    reasons: tuple[str, ...]


class ResolutionV2EvalReport(BaseModel):
    """Quality, stratification, and safe activation report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["awaiting_labels", "partially_labeled", "labeled"]
    total_examples: int
    labeled_examples: int
    overall: MembershipMetrics | None
    by_macro_family: dict[str, MembershipMetrics]
    by_language: dict[str, MembershipMetrics]
    by_source: dict[str, MembershipMetrics]
    by_method: dict[str, MembershipMetrics]
    by_join_key_type: dict[str, MembershipMetrics]
    by_popularity_tier: dict[str, MembershipMetrics]
    family_activation: dict[str, FamilyActivation]


def load_examples(path: Path) -> tuple[ResolutionV2EvalExample, ...]:
    """Load strict JSON Lines without filling any human labels."""
    examples: list[ResolutionV2EvalExample] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            examples.append(ResolutionV2EvalExample.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(
                f"invalid v2 evaluation row at line {line_number}"
            ) from exc
    return tuple(examples)


def _predicted_ids(
    example: ResolutionV2EvalExample,
    taxonomy: GenreTaxonomy,
) -> set[str]:
    return set(example.predicted_genre_ids) - {taxonomy.unresolved_genre_id}


def _expected_ids(example: ResolutionV2EvalExample) -> set[str]:
    if example.label_should_resolve is not True:
        return set()
    return set(example.label_genre_ids)


def _metrics(
    examples: Sequence[ResolutionV2EvalExample],
    taxonomy: GenreTaxonomy,
) -> MembershipMetrics:
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    for example in examples:
        predicted = _predicted_ids(example, taxonomy)
        expected = _expected_ids(example)
        true_positives += len(predicted & expected)
        false_positives += len(predicted - expected)
        false_negatives += len(expected - predicted)
    precision_denominator = true_positives + false_positives
    recall_denominator = true_positives + false_negatives
    return MembershipMetrics(
        labeled_examples=len(examples),
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


def _grouped_metrics(
    examples: Sequence[ResolutionV2EvalExample],
    taxonomy: GenreTaxonomy,
    key: Callable[[ResolutionV2EvalExample], str],
) -> dict[str, MembershipMetrics]:
    groups: dict[str, list[ResolutionV2EvalExample]] = defaultdict(list)
    for example in examples:
        groups[key(example)].append(example)
    return {
        name: _metrics(group, taxonomy)
        for name, group in sorted(groups.items())
    }


def _family_activation(
    taxonomy: GenreTaxonomy,
    labeled: Sequence[ResolutionV2EvalExample],
    family_metrics: dict[str, MembershipMetrics],
    thresholds: ActivationThresholds,
) -> dict[str, FamilyActivation]:
    decisions: dict[str, FamilyActivation] = {}
    for family in taxonomy.macro_families:
        family_id = family.macro_family_id
        metrics = family_metrics.get(family_id)
        family_examples = tuple(
            example
            for example in labeled
            if example.macro_family_id == family_id
        )
        mbid_examples = tuple(
            example
            for example in family_examples
            if example.join_key_type == "mbid"
        )
        mbid_metrics = (
            _metrics(mbid_examples, taxonomy) if mbid_examples else None
        )
        reasons: list[str] = []
        if metrics is None or (
            metrics.labeled_examples
            < thresholds.minimum_labeled_examples_per_family
        ):
            reasons.append("insufficient_labeled_examples")
        if metrics is not None:
            if metrics.precision < thresholds.minimum_precision:
                reasons.append("precision_below_threshold")
            if metrics.recall < thresholds.minimum_recall:
                reasons.append("recall_below_threshold")
        if mbid_metrics is None:
            reasons.append("insufficient_mbid_examples")
        elif mbid_metrics.precision < thresholds.minimum_mbid_precision:
            reasons.append("mbid_precision_below_threshold")
        if family_id == taxonomy.genre_by_id[
            taxonomy.unresolved_genre_id
        ].macro_family_id:
            reasons.append("unclassified_family_not_activatable")
        eligible = not reasons
        decisions[family_id] = FamilyActivation(
            macro_family_id=family_id,
            status="active" if eligible else "candidate",
            production_eligible=eligible,
            labeled_examples=metrics.labeled_examples if metrics else 0,
            precision=metrics.precision if metrics else None,
            recall=metrics.recall if metrics else None,
            mbid_precision=mbid_metrics.precision if mbid_metrics else None,
            reasons=tuple(reasons),
        )
    return decisions


def evaluate_examples(
    examples: Sequence[ResolutionV2EvalExample],
    taxonomy: GenreTaxonomy,
    thresholds: ActivationThresholds,
) -> ResolutionV2EvalReport:
    """Measure only labeled rows; blank rows remain visible in the denominator."""
    labeled = tuple(
        example for example in examples if example.label_should_resolve is not None
    )
    if not labeled:
        return ResolutionV2EvalReport(
            status="awaiting_labels",
            total_examples=len(examples),
            labeled_examples=0,
            overall=None,
            by_macro_family={},
            by_language={},
            by_source={},
            by_method={},
            by_join_key_type={},
            by_popularity_tier={},
            family_activation=_family_activation(
                taxonomy,
                (),
                {},
                thresholds,
            ),
        )
    by_family = _grouped_metrics(
        labeled,
        taxonomy,
        lambda example: example.macro_family_id,
    )
    return ResolutionV2EvalReport(
        status=(
            "labeled"
            if len(labeled) == len(examples)
            else "partially_labeled"
        ),
        total_examples=len(examples),
        labeled_examples=len(labeled),
        overall=_metrics(labeled, taxonomy),
        by_macro_family=by_family,
        by_language=_grouped_metrics(
            labeled,
            taxonomy,
            lambda example: example.language,
        ),
        by_source=_grouped_metrics(
            labeled,
            taxonomy,
            lambda example: example.source_system,
        ),
        by_method=_grouped_metrics(
            labeled,
            taxonomy,
            lambda example: example.predicted_method,
        ),
        by_join_key_type=_grouped_metrics(
            labeled,
            taxonomy,
            lambda example: example.join_key_type,
        ),
        by_popularity_tier=_grouped_metrics(
            labeled,
            taxonomy,
            lambda example: example.popularity_tier,
        ),
        family_activation=_family_activation(
            taxonomy,
            labeled,
            by_family,
            thresholds,
        ),
    )


def persist_family_activation(
    database_path: Path,
    report: ResolutionV2EvalReport,
    taxonomy: GenreTaxonomy,
    *,
    evaluated_at: datetime | None = None,
) -> None:
    """Persist only measured activation decisions in the parallel v2 layer."""
    evaluation_time = evaluated_at or datetime.now(UTC)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_genre_resolution_v2.sql"))
        connection.executemany(
            load_sql("upsert_stg_genre_family_activation_v2.sql"),
            [
                (
                    decision.macro_family_id,
                    decision.status,
                    decision.production_eligible,
                    decision.labeled_examples,
                    decision.precision,
                    decision.recall,
                    decision.mbid_precision,
                    list(decision.reasons),
                    taxonomy.taxonomy_version,
                    evaluation_time,
                )
                for decision in report.family_activation.values()
            ],
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, nargs="?", default=DEFAULT_EVAL_V2_PATH)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Report metrics without updating v2 activation state.",
    )
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument(
        "--resolution-config",
        type=Path,
        default=DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    taxonomy = load_taxonomy(args.taxonomy)
    config = load_resolution_v2_config(args.resolution_config)
    report = evaluate_examples(
        load_examples(args.fixture),
        taxonomy,
        config.activation,
    )
    if not args.no_persist:
        persist_family_activation(args.database, report, taxonomy)
    print(
        json.dumps(
            report.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    overall = report.overall
    if (
        overall is not None
        and overall.labeled_examples
        >= config.activation.minimum_labeled_examples_per_family
        and overall.precision < config.activation.minimum_overall_precision
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
