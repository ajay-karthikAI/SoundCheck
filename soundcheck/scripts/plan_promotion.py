"""Plan a cheap, idempotent promotion of newly complete decision weeks."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, model_validator

from soundcheck.metrics.listening_windows import iso_week_start
from soundcheck.metrics.maturity import GenreWeekAxisMaturity, build_axis_maturity
from soundcheck.metrics.models import MetricEvidence
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.metrics.v2_models import MetricEvidenceV2
from soundcheck.metrics.v2_storage import DuckDBMetricV2Store
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, GenreTaxonomy, load_taxonomy

ArtifactFamily = Literal["v1", "v2"]
CellKey = tuple[date, str]


class AxisPromotionState(BaseModel):
    """Operational readiness and publication state for one artifact family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_family: ArtifactFamily
    source_counts: dict[str, int]
    maturity_states: dict[str, int]
    ready_cell_count: int
    first_eligible_complete_week: date | None
    latest_eligible_complete_week: date | None
    latest_published_week: date | None
    promotion_required: bool

    @model_validator(mode="after")
    def validate_promotion(self) -> AxisPromotionState:
        expected = self.latest_eligible_complete_week is not None and (
            self.latest_published_week is None
            or self.latest_eligible_complete_week > self.latest_published_week
        )
        if self.promotion_required != expected:
            raise ValueError("promotion_required must reflect a newer eligible week")
        return self


class PromotionPlan(BaseModel):
    """One non-mutating decision about whether downstream work is necessary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["decision_promotion_plan"] = "decision_promotion_plan"
    as_of: datetime
    current_iso_week: date
    v1: AxisPromotionState
    v2: AxisPromotionState
    promotion_required: bool

    @model_validator(mode="after")
    def validate_combined_decision(self) -> PromotionPlan:
        if self.promotion_required != (
            self.v1.promotion_required or self.v2.promotion_required
        ):
            raise ValueError("combined promotion must reflect v1 or v2 readiness")
        return self


def build_axis_promotion_state(
    *,
    artifact_family: ArtifactFamily,
    maturity: tuple[GenreWeekAxisMaturity, ...],
    latest_published_week: date | None,
    as_of: datetime,
    eligible_cells: frozenset[CellKey] | None = None,
) -> AxisPromotionState:
    """Summarize closed, decision-ready cells and suppress repeat promotions."""

    current_week = iso_week_start(as_of)
    ready_rows = tuple(
        row
        for row in maturity
        if row.decision_ready
        and row.week_start < current_week
        and (
            eligible_cells is None
            or (row.week_start, row.genre_id) in eligible_cells
        )
    )
    eligible_weeks = tuple(sorted({row.week_start for row in ready_rows}))
    states: Counter[str] = Counter()
    for row in maturity:
        states[row.conversation_maturity] += 1
        states[row.listening_maturity] += 1
        states[row.supply_maturity] += 1
    latest_eligible = eligible_weeks[-1] if eligible_weeks else None
    return AxisPromotionState(
        artifact_family=artifact_family,
        source_counts={
            "conversation_post_genre_weeks": sum(
                row.conversation_post_count for row in maturity
            ),
            "mature_conversation_post_genre_weeks": sum(
                row.mature_conversation_post_count for row in maturity
            ),
            "valid_listening_artist_genre_weeks": sum(
                row.valid_listening_artist_count for row in maturity
            ),
            "musicbrainz_release_genre_weeks": sum(
                row.supply_release_group_count for row in maturity
            ),
        },
        maturity_states=dict(sorted(states.items())),
        ready_cell_count=len(ready_rows),
        first_eligible_complete_week=(eligible_weeks[0] if eligible_weeks else None),
        latest_eligible_complete_week=latest_eligible,
        latest_published_week=latest_published_week,
        promotion_required=latest_eligible is not None
        and (
            latest_published_week is None
            or latest_eligible > latest_published_week
        ),
    )


def _v1_maturity(
    evidence: MetricEvidence,
    taxonomy: GenreTaxonomy,
    as_of: datetime,
) -> tuple[GenreWeekAxisMaturity, ...]:
    weeks = tuple(
        sorted(
            {
                *(row.week_start for row in evidence.conversation),
                *(row.week_start for row in evidence.listening_candidates),
                *(row.week_start for row in evidence.supply),
            }
        )
    )
    return build_axis_maturity(
        artifact_family="v1",
        taxonomy_version="v1",
        weeks=weeks,
        genre_ids=taxonomy.canonical_genres,
        conversation=tuple(
            (row.canonical_genre.casefold(), row) for row in evidence.conversation
        ),
        listening=tuple(
            (row.canonical_genre.casefold(), row)
            for row in evidence.listening_candidates
        ),
        supply=tuple(
            (row.canonical_genre.casefold(), row) for row in evidence.supply
        ),
        supply_windows=evidence.supply_windows,
        computed_at=as_of,
    )


def _v2_maturity(
    evidence: MetricEvidenceV2,
    taxonomy: GenreTaxonomy,
    as_of: datetime,
) -> tuple[GenreWeekAxisMaturity, ...]:
    weeks = tuple(sorted({row.week_start for row in evidence.coverage}))
    return build_axis_maturity(
        artifact_family="v2",
        taxonomy_version=taxonomy.taxonomy_version,
        weeks=weeks,
        genre_ids=tuple(row.genre_id for row in taxonomy.genres),
        conversation=tuple((row.genre_id, row) for row in evidence.conversation),
        listening=tuple(
            (row.genre_id, row) for row in evidence.listening_candidates
        ),
        supply=tuple((row.genre_id, row) for row in evidence.supply),
        supply_windows=evidence.supply_windows,
        computed_at=as_of,
    )


def _v2_eligible_cells(evidence: MetricEvidenceV2) -> frozenset[CellKey]:
    coverage = {
        (row.week_start, row.genre_id)
        for row in evidence.coverage
        if row.eligibility_state == "ready"
    }
    conversation = {
        (row.week_start, row.genre_id)
        for row in evidence.conversation
        if row.engagement_maturity_status == "complete"
    }
    listening = {
        (row.week_start, row.genre_id)
        for row in evidence.listening_candidates
        if row.listening_window_status == "valid_weekly"
    }
    supply = {(row.week_start, row.genre_id) for row in evidence.supply}
    return frozenset(coverage & conversation & listening & supply)


def _published_weeks(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[date | None, date | None]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        try:
            row = connection.execute(
                load_sql("select_published_decision_weeks.sql"),
                [taxonomy_version],
            ).fetchone()
        except duckdb.CatalogException:
            return None, None
    if row is None:
        return None, None
    return row[0], row[1]


async def build_promotion_plan(
    *,
    database_path: Path,
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH,
    as_of: datetime | None = None,
) -> PromotionPlan:
    """Read current evidence and decide whether a full downstream run is needed."""

    observed_at = (as_of or datetime.now(UTC)).astimezone(UTC)
    taxonomy = load_taxonomy(taxonomy_path)
    v1_store = DuckDBMetricStore(database_path)
    v2_store = DuckDBMetricV2Store(database_path)
    v1_evidence = await v1_store.load_evidence(as_of=observed_at)
    v2_evidence = await v2_store.load_evidence(
        taxonomy.taxonomy_version,
        as_of=observed_at,
    )
    published_v1, published_v2 = await asyncio.to_thread(
        _published_weeks,
        database_path,
        taxonomy.taxonomy_version,
    )
    v1 = build_axis_promotion_state(
        artifact_family="v1",
        maturity=_v1_maturity(v1_evidence, taxonomy, observed_at),
        latest_published_week=published_v1,
        as_of=observed_at,
    )
    v2 = build_axis_promotion_state(
        artifact_family="v2",
        maturity=_v2_maturity(v2_evidence, taxonomy, observed_at),
        latest_published_week=published_v2,
        as_of=observed_at,
        eligible_cells=_v2_eligible_cells(v2_evidence),
    )
    return PromotionPlan(
        as_of=observed_at,
        current_iso_week=iso_week_start(observed_at),
        v1=v1,
        v2=v2,
        promotion_required=v1.promotion_required or v2.promotion_required,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument("--format", choices=("json", "github"), default="json")
    return parser


def main() -> None:
    """CLI entrypoint for scheduled readiness checks."""

    args = _build_parser().parse_args()
    plan = asyncio.run(
        build_promotion_plan(
            database_path=args.database,
            taxonomy_path=args.taxonomy,
        )
    )
    if args.format == "github":
        latest = max(
            (
                week
                for week in (
                    plan.v1.latest_eligible_complete_week,
                    plan.v2.latest_eligible_complete_week,
                )
                if week is not None
            ),
            default=None,
        )
        print(f"promotion_required={str(plan.promotion_required).lower()}")
        print(f"latest_eligible_complete_week={latest or ''}")
        print(
            "promotion_plan_json="
            + json.dumps(
                plan.model_dump(mode="json"),
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return
    print(
        json.dumps(
            plan.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
