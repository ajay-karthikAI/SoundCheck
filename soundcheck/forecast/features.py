"""Leakage-safe weekly feature construction for pooled forecasting."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from soundcheck.forecast.models import (
    FeatureVector,
    ForecastHistoryRow,
    TargetAxis,
    TrainingExample,
)

FEATURE_NAMES = (
    "target_lag_1",
    "target_lag_2",
    "target_lag_3",
    "target_lag_4",
    "conversation_ewma",
    "listening_ewma",
    "supply_ewma",
    "conversation_spike",
    "listening_spike",
    "supply_spike",
    "supply_index",
    "discovery_gap",
    "embedding_trend_similarity",
    "week_of_year",
    "genre_id",
)
GENRE_ID_FEATURE_INDEX = len(FEATURE_NAMES) - 1


class ForecastDataset:
    """In-memory mart history with auditable as-of feature access."""

    def __init__(self, rows: tuple[ForecastHistoryRow, ...]) -> None:
        self._rows = {
            (row.canonical_genre, row.week_start): row
            for row in rows
        }
        if len(self._rows) != len(rows):
            msg = "forecast history contains duplicate genre-week rows"
            raise ValueError(msg)
        self.weeks = tuple(sorted({row.week_start for row in rows}))
        self.genres = tuple(sorted({row.canonical_genre for row in rows}))
        self._genre_ids = {
            genre: genre_id for genre_id, genre in enumerate(self.genres)
        }
        embedding_lengths = {
            len(row.genre_embedding)
            for row in rows
            if row.genre_embedding
        }
        if len(embedding_lengths) > 1:
            msg = "genre embeddings must share one dimension"
            raise ValueError(msg)
        self._similarity_cache: dict[tuple[str, date], float] = {}

    def row(
        self,
        canonical_genre: str,
        week_start: date,
    ) -> ForecastHistoryRow | None:
        return self._rows.get((canonical_genre, week_start))

    def target_value(
        self,
        canonical_genre: str,
        week_start: date,
        target_axis: TargetAxis,
    ) -> float | None:
        row = self.row(canonical_genre, week_start)
        if row is None:
            return None
        if target_axis == "conversation":
            return row.conversation_index
        return row.listening_index

    def feature_vector(
        self,
        canonical_genre: str,
        target_axis: TargetAxis,
        horizon: int,
        origin_week: date,
    ) -> FeatureVector | None:
        origin = self.row(canonical_genre, origin_week)
        if origin is None:
            return None
        lags = [
            self.target_value(
                canonical_genre,
                origin_week - timedelta(weeks=offset),
                target_axis,
            )
            for offset in range(4)
        ]
        target_week = origin_week + timedelta(weeks=horizon)
        values = (
            *(_nan_if_none(value) for value in lags),
            origin.conversation_ewma,
            _nan_if_none(origin.listening_ewma),
            origin.supply_ewma,
            float(origin.conversation_spike),
            float(origin.listening_spike),
            float(origin.supply_spike),
            origin.supply_index,
            _nan_if_none(origin.discovery_gap),
            self._embedding_trend_similarity(canonical_genre, origin_week),
            float(target_week.isocalendar().week),
            float(self._genre_ids[canonical_genre]),
        )
        return FeatureVector(
            canonical_genre=canonical_genre,
            target_axis=target_axis,
            horizon=horizon,
            origin_week=origin_week,
            target_week=target_week,
            max_observed_week=origin_week,
            feature_names=FEATURE_NAMES,
            values=values,
        )

    def training_examples(
        self,
        target_axis: TargetAxis,
        horizon: int,
        *,
        target_cutoff_week: date,
    ) -> tuple[TrainingExample, ...]:
        examples: list[TrainingExample] = []
        for target_week in self.weeks:
            if target_week > target_cutoff_week:
                continue
            origin_week = target_week - timedelta(weeks=horizon)
            for genre in self.genres:
                target = self.target_value(genre, target_week, target_axis)
                if target is None:
                    continue
                features = self.feature_vector(
                    genre,
                    target_axis,
                    horizon,
                    origin_week,
                )
                if features is None:
                    continue
                examples.append(
                    TrainingExample(
                        features=features,
                        target_value=target,
                    )
                )
        return tuple(examples)

    def contiguous_history(
        self,
        canonical_genre: str,
        target_axis: TargetAxis,
        origin_week: date,
    ) -> tuple[tuple[date, ...], tuple[float, ...]]:
        weeks: list[date] = []
        values: list[float] = []
        current = origin_week
        while True:
            value = self.target_value(canonical_genre, current, target_axis)
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
        canonical_genre: str,
        target_axis: TargetAxis,
        horizon: int,
        origin_week: date,
    ) -> tuple[float, ...]:
        errors: list[float] = []
        for forecast_origin in self.weeks:
            target_week = forecast_origin + timedelta(weeks=horizon)
            if target_week > origin_week:
                continue
            prediction = self.target_value(
                canonical_genre,
                forecast_origin,
                target_axis,
            )
            actual = self.target_value(
                canonical_genre,
                target_week,
                target_axis,
            )
            if prediction is not None and actual is not None:
                errors.append(actual - prediction)
        return tuple(errors)

    def historical_seasonal_errors(
        self,
        canonical_genre: str,
        target_axis: TargetAxis,
        origin_week: date,
        *,
        period_weeks: int,
    ) -> tuple[float, ...]:
        errors: list[float] = []
        for target_week in self.weeks:
            if target_week > origin_week:
                continue
            previous_cycle = target_week - timedelta(weeks=period_weeks)
            prediction = self.target_value(
                canonical_genre,
                previous_cycle,
                target_axis,
            )
            actual = self.target_value(
                canonical_genre,
                target_week,
                target_axis,
            )
            if prediction is not None and actual is not None:
                errors.append(actual - prediction)
        return tuple(errors)

    def _embedding_trend_similarity(
        self,
        canonical_genre: str,
        week_start: date,
    ) -> float:
        cache_key = (canonical_genre, week_start)
        cached = self._similarity_cache.get(cache_key)
        if cached is not None:
            return cached
        current = self.row(canonical_genre, week_start)
        if current is None or not current.genre_embedding:
            return 0.0
        candidates: list[tuple[float, np.ndarray]] = []
        for genre in self.genres:
            row = self.row(genre, week_start)
            if row is None or not row.genre_embedding:
                continue
            score = (
                row.opportunity
                if row.opportunity is not None
                else row.conversation_index
            )
            candidates.append(
                (
                    score,
                    np.asarray(row.genre_embedding, dtype=np.float64),
                )
            )
        if not candidates:
            return 0.0
        candidates.sort(key=lambda item: item[0], reverse=True)
        centroid = np.mean(
            np.stack([embedding for _score, embedding in candidates[:10]]),
            axis=0,
        )
        vector = np.asarray(current.genre_embedding, dtype=np.float64)
        denominator = float(np.linalg.norm(vector) * np.linalg.norm(centroid))
        similarity = (
            0.0 if denominator <= 1e-12 else float(np.dot(vector, centroid) / denominator)
        )
        self._similarity_cache[cache_key] = similarity
        return similarity


def _nan_if_none(value: float | None) -> float:
    return math.nan if value is None else value
