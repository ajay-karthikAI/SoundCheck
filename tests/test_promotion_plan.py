"""Fixture-only tests for fast, restart-safe decision promotion."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from soundcheck.metrics.maturity import GenreWeekAxisMaturity
from soundcheck.scripts.plan_promotion import build_axis_promotion_state


def _maturity(
    *,
    week: date,
    genre_id: str = "genre_shoegaze",
    complete: bool = True,
) -> GenreWeekAxisMaturity:
    status: Literal["conversation_pending", "complete"] = (
        "complete" if complete else "conversation_pending"
    )
    return GenreWeekAxisMaturity(
        artifact_family="v2",
        taxonomy_version="2.0.0",
        week_start=week,
        genre_id=genre_id,
        conversation_maturity=status,
        listening_maturity="complete",
        supply_maturity="complete",
        decision_ready=complete,
        conversation_post_count=1,
        mature_conversation_post_count=int(complete),
        valid_listening_artist_count=2,
        supply_release_group_count=1,
        computed_at=datetime(2026, 8, 20, 6, tzinfo=UTC),
    )


def test_new_closed_complete_week_requires_promotion() -> None:
    week = date(2026, 8, 10)
    state = build_axis_promotion_state(
        artifact_family="v2",
        maturity=(_maturity(week=week),),
        latest_published_week=date(2026, 8, 3),
        as_of=datetime(2026, 8, 20, 6, tzinfo=UTC),
        eligible_cells=frozenset({(week, "genre_shoegaze")}),
    )

    assert state.promotion_required
    assert state.first_eligible_complete_week == week
    assert state.latest_eligible_complete_week == week
    assert state.ready_cell_count == 1


def test_restart_does_not_repromote_the_same_week() -> None:
    week = date(2026, 8, 10)
    state = build_axis_promotion_state(
        artifact_family="v2",
        maturity=(_maturity(week=week),),
        latest_published_week=week,
        as_of=datetime(2026, 8, 20, 6, tzinfo=UTC),
        eligible_cells=frozenset({(week, "genre_shoegaze")}),
    )

    assert not state.promotion_required
    assert state.ready_cell_count == 1


def test_open_or_pending_weeks_never_trigger_promotion() -> None:
    open_week = date(2026, 8, 17)
    state = build_axis_promotion_state(
        artifact_family="v2",
        maturity=(
            _maturity(week=open_week),
            _maturity(week=date(2026, 8, 10), complete=False),
        ),
        latest_published_week=None,
        as_of=datetime(2026, 8, 20, 6, tzinfo=UTC),
        eligible_cells=frozenset(
            {
                (open_week, "genre_shoegaze"),
                (date(2026, 8, 10), "genre_shoegaze"),
            }
        ),
    )

    assert not state.promotion_required
    assert state.ready_cell_count == 0
    assert state.first_eligible_complete_week is None


def test_v2_pipeline_eligibility_is_preserved_by_gate() -> None:
    week = date(2026, 8, 10)
    state = build_axis_promotion_state(
        artifact_family="v2",
        maturity=(_maturity(week=week),),
        latest_published_week=None,
        as_of=datetime(2026, 8, 20, 6, tzinfo=UTC),
        eligible_cells=frozenset(),
    )

    assert not state.promotion_required
    assert state.ready_cell_count == 0


def test_daily_workflow_promotes_only_newly_complete_weeks() -> None:
    workflow = Path(".github/workflows/weekly.yml").read_text(encoding="utf-8")
    promotion = workflow.index("Plan decision-ready promotion")
    metrics = workflow.index("Compute weekly metrics")
    artifact = workflow.index("Upload immutable database artifact")
    deploy = workflow.index("Deploy the API artifact to Vercel")

    assert promotion < metrics < artifact < deploy
    assert "steps.promotion.outputs.promotion_required == 'true'" in workflow
    assert "uv run python -m soundcheck.scripts.plan_promotion" in workflow
    assert "promotion_plan_json=" in Path(
        "soundcheck/scripts/plan_promotion.py"
    ).read_text(encoding="utf-8")
