"""Fixture-only source-maturity and decision-gating tests."""

from datetime import UTC, date, datetime

from soundcheck.metrics.maturity import SupplyCollectionWindow, build_axis_maturity
from soundcheck.metrics.models import (
    ConversationEvidence,
    ListeningDeltaCandidate,
    MetricEvidence,
    SupplyEvidence,
)
from soundcheck.metrics.pipeline import build_metrics


def _evidence(*, conversation_complete: bool) -> MetricEvidence:
    week = date(2026, 7, 13)
    previous = datetime(2026, 7, 9, 12, tzinfo=UTC)
    current = datetime(2026, 7, 16, 12, tzinfo=UTC)
    return MetricEvidence(
        conversation=(
            ConversationEvidence(
                week_start=week,
                canonical_genre="shoegaze",
                post_uri="at://post/fixture",
                mentions=1,
                likes=3 if conversation_complete else None,
                reposts=1 if conversation_complete else None,
                replies=0 if conversation_complete else None,
                engagement_maturity_status=(
                    "complete" if conversation_complete else "overdue_72h"
                ),
            ),
        ),
        listening_candidates=(
            ListeningDeltaCandidate(
                week_start=week,
                canonical_genre="shoegaze",
                artist_key="mbid:artist",
                artist_name="Fixture Artist",
                playcount=1_100,
                listeners=110,
                previous_playcount=1_000,
                previous_listeners=100,
                previous_fetched_at=previous,
                fetched_at=current,
            ),
        ),
        supply=(
            SupplyEvidence(
                week_start=week,
                canonical_genre="shoegaze",
                release_group_mbid="release-1",
            ),
        ),
        supply_windows=(
            SupplyCollectionWindow(
                start_date=week,
                end_date=date(2026, 7, 19),
                completed_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
            ),
        ),
    )


def test_missing_engagement_remains_pending_and_cannot_score() -> None:
    batch = build_metrics(
        _evidence(conversation_complete=False),
        ("shoegaze", "ambient"),
        computed_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
        bootstrap_resamples=20,
    )
    maturity = next(
        row for row in batch.axis_maturity if row.genre_id == "shoegaze"
    )
    metric = next(row for row in batch.genre_weeks if row.canonical_genre == "shoegaze")
    assert maturity.conversation_maturity == "conversation_pending"
    assert maturity.mature_conversation_post_count == 0
    assert not maturity.decision_ready
    assert metric.opportunity is None
    assert metric.discovery_gap is None
    assert metric.conversation_post_uris == ()


def test_incomplete_and_open_supply_windows_stay_pending() -> None:
    evidence = _evidence(conversation_complete=True)
    conversation = tuple(
        (item.canonical_genre, item) for item in evidence.conversation
    )
    listening = tuple(
        (item.canonical_genre, item) for item in evidence.listening_candidates
    )
    supply = tuple((item.canonical_genre, item) for item in evidence.supply)
    incomplete = build_axis_maturity(
        artifact_family="v1",
        taxonomy_version="v1",
        weeks=(date(2026, 7, 13),),
        genre_ids=("shoegaze",),
        conversation=conversation,
        listening=listening,
        supply=supply,
        supply_windows=(
            SupplyCollectionWindow(
                start_date=date(2026, 7, 13),
                end_date=date(2026, 7, 18),
                completed_at=datetime(2026, 7, 20, 8, tzinfo=UTC),
            ),
        ),
        computed_at=datetime(2026, 7, 20, 12, tzinfo=UTC),
    )[0]
    assert incomplete.supply_maturity == "supply_pending"
    assert not incomplete.decision_ready

    open_week = build_axis_maturity(
        artifact_family="v1",
        taxonomy_version="v1",
        weeks=(date(2026, 7, 20),),
        genre_ids=("shoegaze",),
        conversation=(),
        listening=(),
        supply=(),
        supply_windows=(
            SupplyCollectionWindow(
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 26),
                completed_at=datetime(2026, 7, 22, 8, tzinfo=UTC),
            ),
        ),
        computed_at=datetime(2026, 7, 22, 12, tzinfo=UTC),
    )[0]
    assert open_week.supply_maturity == "supply_pending"
