"""Synthetic, network-free validation for taxonomy-v2 forecasting."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from soundcheck.forecast.v2_features import ForecastDatasetV2
from soundcheck.forecast.v2_models import (
    ForecastHistoryRowV2,
    ModelScoreV2,
    ValidationScope,
)
from soundcheck.forecast.v2_pipeline import (
    BacktestConfigV2,
    build_forecasts_v2,
    model_beats_relevant_naive,
    run_backtest_v2,
    score_backtests_v2,
)
from soundcheck.taxonomy import GenreTaxonomy

START_WEEK_V2 = date(2025, 1, 6)


def test_new_genres_publish_insufficient_history_without_skill_claim() -> None:
    taxonomy = _taxonomy()
    rows = _history(taxonomy, weeks=7)
    batch = build_forecasts_v2(
        rows,
        taxonomy,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
        config=_small_config(),
    )

    prediction = next(
        row
        for row in batch.predictions
        if row.genre_id == "genre_rock_child"
    )
    assert prediction.forecast_status == "insufficient_history"
    assert prediction.valid_training_weeks == 7
    assert prediction.model_name is None
    assert prediction.prediction is None
    assert prediction.backtest_mase is None
    scores = [
        row
        for row in batch.model_scores
        if row.validation_scope == "genre"
        and row.genre_id == "genre_rock_child"
    ]
    assert {row.model_name for row in scores} == {
        "naive",
        "seasonal_naive",
        "ets",
        "lightgbm",
    }
    assert all(row.score_status == "insufficient_history" for row in scores)


def test_features_and_training_targets_are_unchanged_by_future_mutation() -> None:
    taxonomy = _taxonomy()
    rows = _history(taxonomy, weeks=20)
    cutoff = START_WEEK_V2 + timedelta(weeks=12)
    changed = tuple(
        row.model_copy(
            update={
                "conversation": 999_999.0,
                "listening": -999_999.0,
                "conversation_ewma": 999_999.0,
            }
        )
        if row.week_start > cutoff
        else row
        for row in rows
    )
    original = ForecastDatasetV2(rows)
    mutated = ForecastDatasetV2(changed)

    assert original.feature_vector(
        "genre_rock_child",
        "global",
        "conversation",
        2,
        cutoff,
    ) == mutated.feature_vector(
        "genre_rock_child",
        "global",
        "conversation",
        2,
        cutoff,
    )
    examples = mutated.training_examples(
        "global",
        "conversation",
        2,
        target_cutoff_week=cutoff,
    )
    assert examples
    assert all(example.features.target_week <= cutoff for example in examples)
    assert all(
        example.features.max_observed_week <= example.features.origin_week
        < example.features.target_week
        for example in examples
    )


def test_skill_requires_genre_and_relevant_family_tier_to_beat_naive() -> None:
    genre_score = _score(
        scope="genre",
        group_id="genre_rock_child:middle",
        genre_id="genre_rock_child",
        family_id="macro_rock",
        mase=0.7,
    )
    wrong_family = _score(
        scope="family_popularity",
        group_id="macro_pop:middle",
        genre_id=None,
        family_id="macro_pop",
        mase=0.6,
    )
    unskilled_family = _score(
        scope="family_popularity",
        group_id="macro_rock:middle",
        genre_id=None,
        family_id="macro_rock",
        mase=1.1,
    )
    skilled_family = unskilled_family.model_copy(update={"mase": 0.8})

    assert not model_beats_relevant_naive(genre_score, wrong_family)
    assert not model_beats_relevant_naive(genre_score, unskilled_family)
    assert model_beats_relevant_naive(genre_score, skilled_family)


def test_backtests_are_stratified_and_intervals_have_empirical_coverage() -> None:
    taxonomy = _taxonomy()
    rows = _history(taxonomy, weeks=36)
    dataset = ForecastDatasetV2(rows)
    config = _small_config()
    records = run_backtest_v2(dataset, config=config)
    scores = score_backtests_v2(
        records,
        dataset,
        taxonomy,
        config=config,
        evaluated_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert records
    assert all(record.training_weeks >= 8 for record in records)
    assert all(record.max_feature_week == record.origin_week for record in records)
    assert all(record.origin_week < record.target_week for record in records)
    assert {
        (row.validation_scope, row.macro_family_id, row.popularity_tier)
        for row in scores
        if row.score_status in {"scored", "zero_naive_scale"}
    } >= {
        ("family_popularity", "macro_rock", "low"),
        ("family_popularity", "macro_rock", "high"),
    }
    naive_coverages = [
        row.interval_coverage_80
        for row in scores
        if row.validation_scope == "genre"
        and row.model_name == "naive"
        and row.interval_coverage_80 is not None
    ]
    assert naive_coverages
    assert all(0.50 <= coverage <= 1.0 for coverage in naive_coverages)


def test_zero_scale_series_is_no_skill_and_keeps_baseline() -> None:
    taxonomy = _taxonomy()
    rows = _history(taxonomy, weeks=12, constant=True)
    batch = build_forecasts_v2(
        rows,
        taxonomy,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
        config=_small_config(),
    )
    prediction = next(
        row
        for row in batch.predictions
        if row.genre_id == "genre_rock_child"
    )

    assert prediction.forecast_status == "no_skill"
    assert prediction.model_name == "naive"
    assert prediction.backtest_score_status == "zero_naive_scale"
    assert prediction.backtest_mase is None
    assert prediction.naive_prediction == prediction.prediction
    assert prediction.interval_low is not None
    assert prediction.prediction is not None
    assert prediction.interval_high is not None
    assert prediction.interval_low <= prediction.prediction <= prediction.interval_high


def _small_config() -> BacktestConfigV2:
    return BacktestConfigV2(
        horizons=(1,),
        target_axes=("conversation",),
        contexts=("global",),
        gbm_estimators=10,
    )


def _history(
    taxonomy: GenreTaxonomy,
    *,
    weeks: int,
    constant: bool = False,
) -> tuple[ForecastHistoryRowV2, ...]:
    rows: list[ForecastHistoryRowV2] = []
    genre_ids = (
        "genre_rock_child",
        "genre_rock_peer",
        "genre_pop_child",
        "genre_pop_peer",
    )
    definitions = taxonomy.genre_by_id
    for week_number in range(weeks):
        week_start = START_WEEK_V2 + timedelta(weeks=week_number)
        for genre_number, genre_id in enumerate(genre_ids):
            definition = definitions[genre_id]
            trend = 0.0 if constant else 0.08 * week_number
            noise = (
                0.0
                if constant
                else 0.08 * math.sin(week_number * 1.3 + genre_number)
            )
            conversation = trend + noise + genre_number * 0.03
            listening = trend * 0.8 - noise + genre_number * 0.02
            supply = 0.0 if constant else math.sin(week_number / 4.0) * 0.1
            for context in ("global", "peer_family"):
                context_shift = 0.0 if context == "global" else genre_number * 0.01
                rows.append(
                    ForecastHistoryRowV2(
                        taxonomy_version=taxonomy.taxonomy_version,
                        week_start=week_start,
                        genre_id=genre_id,
                        display_name=definition.display_name,
                        macro_family_id=definition.macro_family_id,
                        parent_genre_id=definition.parent_genre_id,
                        taxonomy_status=definition.status,
                        coverage_state="ready",
                        estimate_eligible=True,
                        context=context,
                        conversation=conversation + context_shift,
                        listening=listening + context_shift,
                        supply=supply + context_shift,
                        discovery_gap=listening - conversation,
                        opportunity=(conversation + listening) / 2.0 - supply,
                        conversation_ewma=conversation - 0.03,
                        listening_ewma=listening - 0.02,
                        supply_ewma=supply,
                        conversation_spike=False,
                        listening_spike=False,
                        supply_spike=False,
                        conversation_effective_n=float(10 + genre_number * 100),
                        listening_effective_n=float(20 + genre_number * 100),
                    )
                )
    return tuple(rows)


def _score(
    *,
    scope: ValidationScope,
    group_id: str,
    genre_id: str | None,
    family_id: str,
    mase: float,
) -> ModelScoreV2:
    return ModelScoreV2(
        taxonomy_version="2.0.0",
        validation_scope=scope,
        validation_group_id=group_id,
        genre_id=genre_id,
        macro_family_id=family_id,
        popularity_tier="middle",
        context="global",
        target_axis="conversation",
        horizon=1,
        model_name="ets",
        backtest_start_week=date(2025, 3, 3),
        backtest_end_week=date(2025, 4, 7),
        origin_count=6,
        mae=mase,
        naive_mae=1.0,
        mase=mase,
        interval_coverage_80=0.8,
        mean_interval_width=0.5,
        score_status="scored",
        evaluated_at=datetime(2026, 7, 27, tzinfo=UTC),
    )


def _taxonomy() -> GenreTaxonomy:
    genres = [
        _genre("genre_rock_root", "Rock", "rock", "macro_rock", None),
        _genre(
            "genre_rock_child",
            "Rock Child",
            "rock-child",
            "macro_rock",
            "genre_rock_root",
        ),
        _genre(
            "genre_rock_peer",
            "Rock Peer",
            "rock-peer",
            "macro_rock",
            "genre_rock_root",
        ),
        _genre("genre_pop_root", "Pop", "pop", "macro_pop", None),
        _genre(
            "genre_pop_child",
            "Pop Child",
            "pop-child",
            "macro_pop",
            "genre_pop_root",
        ),
        _genre(
            "genre_pop_peer",
            "Pop Peer",
            "pop-peer",
            "macro_pop",
            "genre_pop_root",
        ),
        _genre("genre_other", "Other", "other", "macro_unclassified", None),
        _genre(
            "genre_unresolved",
            "Unresolved",
            "unresolved",
            "macro_unclassified",
            None,
        ),
    ]
    return GenreTaxonomy.model_validate(
        {
            "taxonomy_version": "2.0.0",
            "default_genre_id": "genre_rock_child",
            "other_genre_id": "genre_other",
            "unresolved_genre_id": "genre_unresolved",
            "macro_families": [
                {
                    "macro_family_id": "macro_pop",
                    "display_name": "Pop",
                    "slug": "pop",
                },
                {
                    "macro_family_id": "macro_rock",
                    "display_name": "Rock",
                    "slug": "rock",
                },
                {
                    "macro_family_id": "macro_unclassified",
                    "display_name": "Unclassified",
                    "slug": "unclassified",
                },
            ],
            "genres": genres,
            "production_compatibility": {
                "canonical_genre_ids": ["genre_rock_child"],
                "lastfm_collection_tags": ["rock child"],
                "musicbrainz_collection_tags": ["rock child"],
                "manual_overrides": {},
            },
        }
    )


def _genre(
    genre_id: str,
    display_name: str,
    slug: str,
    family_id: str,
    parent_id: str | None,
) -> dict[str, object]:
    source_name = display_name.casefold()
    return {
        "genre_id": genre_id,
        "display_name": display_name,
        "slug": slug,
        "macro_family_id": family_id,
        "parent_genre_id": parent_id,
        "aliases": [],
        "multilingual_aliases": {},
        "lastfm_spelling_variants": [source_name],
        "musicbrainz_spelling_variants": [source_name],
        "status": "enabled",
        "taxonomy_version": "2.0.0",
    }
