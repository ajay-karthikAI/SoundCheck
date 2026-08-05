"""Leakage-auditable taxonomy and macro-family features for forecast v2."""

from __future__ import annotations

import math
from datetime import date, timedelta

from soundcheck.forecast.models import FeatureVector, TargetAxis, TrainingExample
from soundcheck.forecast.v2_models import (
    ForecastHistoryRowV2,
    PopularityTier,
)
from soundcheck.metrics.v2_models import MetricContext

FEATURE_NAMES_V2 = (
    "target_asof_0",
    "target_lag_1",
    "target_lag_2",
    "target_lag_3",
    "conversation_ewma",
    "listening_ewma",
    "supply_ewma",
    "conversation_spike",
    "listening_spike",
    "supply_spike",
    "supply_index",
    "discovery_gap",
    "family_conversation_asof_mean",
    "family_listening_asof_mean",
    "family_observed_genres",
    "week_of_year",
    "genre_id",
    "macro_family_id",
    "parent_genre_id",
    "taxonomy_version",
    "context",
    "popularity_tier",
)
CATEGORICAL_FEATURE_INDICES_V2 = (16, 17, 18, 19, 20, 21)


class ForecastDatasetV2:
    """In-memory taxonomy-v2 history with strict as-of access."""

    def __init__(self, rows: tuple[ForecastHistoryRowV2, ...]) -> None:
        self._rows = {
            (row.genre_id, row.context, row.week_start): row
            for row in rows
        }
        if len(self._rows) != len(rows):
            raise ValueError("v2 forecast history contains duplicate keys")
        versions = {row.taxonomy_version for row in rows}
        if len(versions) > 1:
            raise ValueError("v2 forecast history cannot mix taxonomy versions")
        self.taxonomy_version = next(iter(versions), "")
        self.weeks = tuple(sorted({row.week_start for row in rows}))
        self.genres = tuple(sorted({row.genre_id for row in rows}))
        self.contexts = tuple(sorted({row.context for row in rows}))
        self._genre_ids = _codes(self.genres)
        self._family_ids = _codes(
            tuple(sorted({row.macro_family_id for row in rows}))
        )
        self._parent_ids = _codes(
            tuple(sorted({row.parent_genre_id or "__root__" for row in rows}))
        )
        self._version_ids = _codes(tuple(sorted(versions)))
        self._context_ids = _codes(("global", "peer_family"))
        self._tier_ids = _codes(("low", "middle", "high", "unknown"))

    def row(
        self,
        genre_id: str,
        context: MetricContext,
        week_start: date,
    ) -> ForecastHistoryRowV2 | None:
        return self._rows.get((genre_id, context, week_start))

    def target_value(
        self,
        genre_id: str,
        context: MetricContext,
        week_start: date,
        target_axis: TargetAxis,
    ) -> float | None:
        row = self.row(genre_id, context, week_start)
        if row is None:
            return None
        return row.conversation if target_axis == "conversation" else row.listening

    def popularity_tier(
        self,
        genre_id: str,
        context: MetricContext,
        origin_week: date,
    ) -> PopularityTier:
        """Classify popularity from only origin-or-earlier effective evidence."""
        current = self.row(genre_id, context, origin_week)
        if current is None:
            return "unknown"
        signals: list[tuple[float, str]] = []
        for candidate in self.genres:
            row = self.row(candidate, context, origin_week)
            if row is None or row.macro_family_id != current.macro_family_id:
                continue
            components = tuple(
                value
                for value in (
                    row.conversation_effective_n,
                    row.listening_effective_n,
                )
                if value is not None
            )
            if components:
                signals.append((math.fsum(components), candidate))
        if not signals:
            return "unknown"
        signals.sort(key=lambda item: (item[0], item[1]))
        own_ranks = tuple(
            index
            for index, (_signal, candidate) in enumerate(signals)
            if candidate == genre_id
        )
        if not own_ranks:
            return "unknown"
        if len(signals) == 1:
            return "middle"
        rank = own_ranks[0]
        percentile = rank / (len(signals) - 1)
        if percentile < 1.0 / 3.0:
            return "low"
        if percentile > 2.0 / 3.0:
            return "high"
        return "middle"

    def feature_vector(
        self,
        genre_id: str,
        context: MetricContext,
        target_axis: TargetAxis,
        horizon: int,
        origin_week: date,
    ) -> FeatureVector | None:
        """Build features known at the origin; target-week calendar is deterministic."""
        origin = self.row(genre_id, context, origin_week)
        if origin is None:
            return None
        lags = tuple(
            self.target_value(
                genre_id,
                context,
                origin_week - timedelta(weeks=offset),
                target_axis,
            )
            for offset in range(4)
        )
        family_rows = tuple(
            row
            for candidate in self.genres
            if (
                (row := self.row(candidate, context, origin_week)) is not None
                and row.macro_family_id == origin.macro_family_id
            )
        )
        family_conversation = tuple(
            row.conversation
            for row in family_rows
            if row.conversation is not None
        )
        family_listening = tuple(
            row.listening for row in family_rows if row.listening is not None
        )
        tier = self.popularity_tier(genre_id, context, origin_week)
        target_week = origin_week + timedelta(weeks=horizon)
        values = (
            *(_nan(value) for value in lags),
            _nan(origin.conversation_ewma),
            _nan(origin.listening_ewma),
            _nan(origin.supply_ewma),
            _flag(origin.conversation_spike),
            _flag(origin.listening_spike),
            _flag(origin.supply_spike),
            _nan(origin.supply),
            _nan(origin.discovery_gap),
            _mean_or_nan(family_conversation),
            _mean_or_nan(family_listening),
            float(len(family_rows)),
            float(target_week.isocalendar().week),
            float(self._genre_ids[genre_id]),
            float(self._family_ids[origin.macro_family_id]),
            float(self._parent_ids[origin.parent_genre_id or "__root__"]),
            float(self._version_ids[origin.taxonomy_version]),
            float(self._context_ids[context]),
            float(self._tier_ids[tier]),
        )
        return FeatureVector(
            canonical_genre=genre_id,
            target_axis=target_axis,
            horizon=horizon,
            origin_week=origin_week,
            target_week=target_week,
            max_observed_week=origin_week,
            feature_names=FEATURE_NAMES_V2,
            values=values,
        )

    def training_examples(
        self,
        context: MetricContext,
        target_axis: TargetAxis,
        horizon: int,
        *,
        target_cutoff_week: date,
    ) -> tuple[TrainingExample, ...]:
        """Pool genres globally while holding every target at or before cutoff."""
        examples: list[TrainingExample] = []
        for target_week in self.weeks:
            if target_week > target_cutoff_week:
                continue
            origin_week = target_week - timedelta(weeks=horizon)
            for genre_id in self.genres:
                target = self.target_value(
                    genre_id,
                    context,
                    target_week,
                    target_axis,
                )
                if target is None:
                    continue
                features = self.feature_vector(
                    genre_id,
                    context,
                    target_axis,
                    horizon,
                    origin_week,
                )
                if features is not None:
                    examples.append(
                        TrainingExample(
                            features=features,
                            target_value=target,
                        )
                    )
        return tuple(examples)

    def contiguous_history(
        self,
        genre_id: str,
        context: MetricContext,
        target_axis: TargetAxis,
        origin_week: date,
    ) -> tuple[tuple[date, ...], tuple[float, ...]]:
        """Return the latest uninterrupted run; missing weeks break history."""
        weeks: list[date] = []
        values: list[float] = []
        current = origin_week
        while True:
            value = self.target_value(
                genre_id,
                context,
                current,
                target_axis,
            )
            if value is None:
                break
            weeks.append(current)
            values.append(value)
            current -= timedelta(weeks=1)
        weeks.reverse()
        values.reverse()
        return tuple(weeks), tuple(values)

    def historical_persistence_errors(
        self,
        genre_id: str,
        context: MetricContext,
        target_axis: TargetAxis,
        horizon: int,
        origin_week: date,
    ) -> tuple[float, ...]:
        errors: list[float] = []
        for forecast_origin in self.weeks:
            target_week = forecast_origin + timedelta(weeks=horizon)
            if target_week > origin_week:
                continue
            point = self.target_value(
                genre_id,
                context,
                forecast_origin,
                target_axis,
            )
            actual = self.target_value(
                genre_id,
                context,
                target_week,
                target_axis,
            )
            if point is not None and actual is not None:
                errors.append(actual - point)
        return tuple(errors)

    def historical_seasonal_errors(
        self,
        genre_id: str,
        context: MetricContext,
        target_axis: TargetAxis,
        origin_week: date,
        *,
        period_weeks: int,
    ) -> tuple[float, ...]:
        errors: list[float] = []
        for target_week in self.weeks:
            if target_week > origin_week:
                continue
            point = self.target_value(
                genre_id,
                context,
                target_week - timedelta(weeks=period_weeks),
                target_axis,
            )
            actual = self.target_value(
                genre_id,
                context,
                target_week,
                target_axis,
            )
            if point is not None and actual is not None:
                errors.append(actual - point)
        return tuple(errors)


def _codes(values: tuple[str, ...]) -> dict[str, int]:
    return {value: index for index, value in enumerate(values)}


def _nan(value: float | None) -> float:
    return math.nan if value is None else value


def _flag(value: bool | None) -> float:
    return math.nan if value is None else float(value)


def _mean_or_nan(values: tuple[float, ...]) -> float:
    return math.nan if not values else math.fsum(values) / len(values)
