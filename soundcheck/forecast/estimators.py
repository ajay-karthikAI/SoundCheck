"""Forecast estimators and training-only interval construction."""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np
from lightgbm import LGBMRegressor, log_evaluation
from statsmodels.tsa.holtwinters import (  # type: ignore[import-untyped]
    ExponentialSmoothing,
)

from soundcheck.forecast.features import GENRE_ID_FEATURE_INDEX, ForecastDataset
from soundcheck.forecast.models import (
    FeatureVector,
    ForecastEstimate,
    TargetAxis,
    TrainingExample,
)

SEASONAL_PERIOD_WEEKS = 52
DEFAULT_GBM_ESTIMATORS = 80
MIN_GLOBAL_TRAINING_EXAMPLES = 16


def naive_forecast(
    dataset: ForecastDataset,
    canonical_genre: str,
    target_axis: TargetAxis,
    horizon: int,
    origin_week: date,
) -> ForecastEstimate | None:
    """Persistence forecast with an interval from prior h-step changes."""
    point = dataset.target_value(
        canonical_genre,
        origin_week,
        target_axis,
    )
    if point is None:
        return None
    errors = dataset.historical_persistence_errors(
        canonical_genre,
        target_axis,
        horizon,
        origin_week,
    )
    return _residual_interval(point, errors)


def seasonal_naive_forecast(
    dataset: ForecastDataset,
    canonical_genre: str,
    target_axis: TargetAxis,
    horizon: int,
    origin_week: date,
) -> ForecastEstimate | None:
    """Forecast the target from the same ISO week one 52-week cycle earlier."""
    target_week = origin_week + timedelta(weeks=horizon)
    previous_cycle = target_week - timedelta(weeks=SEASONAL_PERIOD_WEEKS)
    point = dataset.target_value(
        canonical_genre,
        previous_cycle,
        target_axis,
    )
    if point is None:
        return None
    errors = dataset.historical_seasonal_errors(
        canonical_genre,
        target_axis,
        origin_week,
        period_weeks=SEASONAL_PERIOD_WEEKS,
    )
    return _residual_interval(point, errors)


def ets_forecast(
    history: Sequence[float],
    horizon: int,
) -> ForecastEstimate | None:
    """Per-genre additive ETS, adding annual seasonality only after two cycles."""
    values = np.asarray(history, dtype=np.float64)
    if len(values) < 8 or np.any(~np.isfinite(values)):
        return None
    seasonal = "add" if len(values) >= 2 * SEASONAL_PERIOD_WEEKS else None
    seasonal_periods = SEASONAL_PERIOD_WEEKS if seasonal is not None else None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(
                values,
                trend="add",
                damped_trend=True,
                seasonal=seasonal,
                seasonal_periods=seasonal_periods,
                initialization_method="estimated",
            ).fit(optimized=True, remove_bias=True)
            point = float(np.asarray(fit.forecast(horizon), dtype=np.float64)[-1])
            fitted = np.asarray(fit.fittedvalues, dtype=np.float64)
    except (ArithmeticError, RuntimeError, ValueError):
        return None
    residuals = values - fitted
    residuals = residuals[np.isfinite(residuals)] * math.sqrt(horizon)
    return _residual_interval(point, residuals.tolist())


def lightgbm_forecasts(
    examples: Sequence[TrainingExample],
    prediction_features: Sequence[FeatureVector],
    *,
    estimators: int = DEFAULT_GBM_ESTIMATORS,
    categorical_feature_indices: Sequence[int] = (GENRE_ID_FEATURE_INDEX,),
) -> dict[str, ForecastEstimate]:
    """Fit pooled point/lower/upper LightGBM models across genres."""
    if len(examples) < MIN_GLOBAL_TRAINING_EXAMPLES or not prediction_features:
        return {}
    feature_names = examples[0].features.feature_names
    if any(example.features.feature_names != feature_names for example in examples):
        msg = "training examples use inconsistent feature schemas"
        raise ValueError(msg)
    if any(features.feature_names != feature_names for features in prediction_features):
        msg = "prediction features use inconsistent feature schemas"
        raise ValueError(msg)
    training_matrix = np.asarray(
        [example.features.values for example in examples],
        dtype=np.float64,
    )
    targets = np.asarray(
        [example.target_value for example in examples],
        dtype=np.float64,
    )
    prediction_matrix = np.asarray(
        [features.values for features in prediction_features],
        dtype=np.float64,
    )
    point_model = _gbm_model("regression_l1", estimators=estimators)
    lower_model = _gbm_model("quantile", alpha=0.10, estimators=estimators)
    upper_model = _gbm_model("quantile", alpha=0.90, estimators=estimators)
    point_model.fit(
        training_matrix,
        targets,
        categorical_feature=list(categorical_feature_indices),
        callbacks=[log_evaluation(0)],
    )
    lower_model.fit(
        training_matrix,
        targets,
        categorical_feature=list(categorical_feature_indices),
        callbacks=[log_evaluation(0)],
    )
    upper_model.fit(
        training_matrix,
        targets,
        categorical_feature=list(categorical_feature_indices),
        callbacks=[log_evaluation(0)],
    )
    points = np.asarray(point_model.predict(prediction_matrix), dtype=np.float64)
    lowers = np.asarray(lower_model.predict(prediction_matrix), dtype=np.float64)
    uppers = np.asarray(upper_model.predict(prediction_matrix), dtype=np.float64)
    return {
        features.canonical_genre: ForecastEstimate(
            prediction=float(point),
            interval_low=min(float(lower), float(upper), float(point)),
            interval_high=max(float(lower), float(upper), float(point)),
        )
        for features, point, lower, upper in zip(
            prediction_features,
            points,
            lowers,
            uppers,
            strict=True,
        )
    }


def _gbm_model(
    objective: str,
    *,
    estimators: int,
    alpha: float | None = None,
) -> LGBMRegressor:
    if alpha is None:
        return LGBMRegressor(
            objective=objective,
            n_estimators=estimators,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=3,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=0.1,
            random_state=20260723,
            n_jobs=1,
            verbosity=-1,
        )
    return LGBMRegressor(
        objective=objective,
        alpha=alpha,
        n_estimators=estimators,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=3,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=0.1,
        random_state=20260723,
        n_jobs=1,
        verbosity=-1,
    )


def _residual_interval(
    point: float,
    residuals: Sequence[float],
) -> ForecastEstimate:
    finite = np.asarray(
        [residual for residual in residuals if math.isfinite(residual)],
        dtype=np.float64,
    )
    if len(finite) == 0:
        return ForecastEstimate(
            prediction=point,
            interval_low=point,
            interval_high=point,
        )
    lower_residual, upper_residual = np.quantile(finite, [0.10, 0.90])
    return ForecastEstimate(
        prediction=point,
        interval_low=min(point, point + float(lower_residual)),
        interval_high=max(point, point + float(upper_residual)),
    )
