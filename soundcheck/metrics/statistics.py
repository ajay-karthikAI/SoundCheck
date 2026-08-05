"""Pure statistical primitives for weekly Soundcheck metrics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

_EPSILON = 1e-12
_MAX_PRIOR_CONCENTRATION = 1_000_000.0


@dataclass(frozen=True, slots=True)
class BetaBinomialResult:
    """Empirical-Bayes posterior for mutually exclusive conversation shares."""

    observed_shares: FloatArray
    posterior_shares: FloatArray
    posterior_counts: FloatArray
    prior_mean: float
    prior_concentration: float
    effective_n: float
    shrinkage_weight: float


@dataclass(frozen=True, slots=True)
class GammaPoissonResult:
    """Empirical-Bayes posterior rates for genre-week supply counts."""

    posterior_rates: FloatArray
    prior_mean: float
    prior_shape: float
    prior_rate: float
    effective_n: float
    shrinkage_weight: float


def within_week_zscores(values: Sequence[float | None]) -> FloatArray:
    """Population z-scores over the observed values in exactly one ISO week."""
    array = np.asarray(
        [np.nan if value is None else value for value in values],
        dtype=np.float64,
    )
    observed = np.isfinite(array)
    if not np.any(observed):
        return array
    mean = float(np.mean(array[observed]))
    standard_deviation = float(np.std(array[observed], ddof=0))
    result = np.full(array.shape, np.nan, dtype=np.float64)
    if standard_deviation <= _EPSILON:
        result[observed] = 0.0
    else:
        result[observed] = (array[observed] - mean) / standard_deviation
        result[observed] -= float(np.mean(result[observed]))
    return result


def beta_binomial_shrink(
    counts: Sequence[float] | FloatArray,
) -> BetaBinomialResult:
    """Shrink conversation shares toward the symmetric cross-genre prior."""
    values = np.asarray(counts, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        msg = "counts must be a non-empty one-dimensional sequence"
        raise ValueError(msg)
    if np.any(values < 0):
        msg = "counts cannot be negative"
        raise ValueError(msg)

    genre_count = len(values)
    total = float(np.sum(values))
    prior_mean = 1.0 / genre_count
    if total <= _EPSILON:
        observed_shares = np.zeros(genre_count, dtype=np.float64)
        posterior_shares = np.full(genre_count, prior_mean, dtype=np.float64)
        return BetaBinomialResult(
            observed_shares=observed_shares,
            posterior_shares=posterior_shares,
            posterior_counts=np.zeros(genre_count, dtype=np.float64),
            prior_mean=prior_mean,
            prior_concentration=float(genre_count),
            effective_n=0.0,
            shrinkage_weight=1.0,
        )

    observed_shares = values / total
    observed_variance = float(np.var(observed_shares, ddof=0))
    sampling_variance = prior_mean * (1.0 - prior_mean) / total
    latent_variance = max(observed_variance - sampling_variance, _EPSILON)
    concentration = prior_mean * (1.0 - prior_mean) / latent_variance - 1.0
    concentration = min(
        max(concentration, _EPSILON),
        _MAX_PRIOR_CONCENTRATION,
    )
    alpha = prior_mean * concentration
    posterior_shares = (values + alpha) / (total + concentration)
    shrinkage_weight = concentration / (total + concentration)
    return BetaBinomialResult(
        observed_shares=observed_shares,
        posterior_shares=posterior_shares,
        posterior_counts=posterior_shares * total,
        prior_mean=prior_mean,
        prior_concentration=concentration,
        effective_n=total,
        shrinkage_weight=shrinkage_weight,
    )


def gamma_poisson_shrink(
    counts: Sequence[float] | FloatArray,
) -> GammaPoissonResult:
    """Shrink supply counts toward a fitted weekly Gamma-Poisson prior."""
    values = np.asarray(counts, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        msg = "counts must be a non-empty one-dimensional sequence"
        raise ValueError(msg)
    if np.any(values < 0):
        msg = "counts cannot be negative"
        raise ValueError(msg)

    prior_mean = float(np.mean(values))
    if prior_mean <= _EPSILON:
        return GammaPoissonResult(
            posterior_rates=np.zeros(len(values), dtype=np.float64),
            prior_mean=0.0,
            prior_shape=1.0,
            prior_rate=_MAX_PRIOR_CONCENTRATION,
            effective_n=1.0,
            shrinkage_weight=1.0,
        )

    observed_variance = float(np.var(values, ddof=0))
    if observed_variance > prior_mean + _EPSILON:
        prior_shape = prior_mean**2 / (observed_variance - prior_mean)
    else:
        prior_shape = _MAX_PRIOR_CONCENTRATION
    prior_shape = min(max(prior_shape, _EPSILON), _MAX_PRIOR_CONCENTRATION)
    prior_rate = prior_shape / prior_mean
    posterior_rates = (values + prior_shape) / (1.0 + prior_rate)
    shrinkage_weight = prior_rate / (1.0 + prior_rate)
    return GammaPoissonResult(
        posterior_rates=posterior_rates,
        prior_mean=prior_mean,
        prior_shape=prior_shape,
        prior_rate=prior_rate,
        effective_n=1.0,
        shrinkage_weight=shrinkage_weight,
    )


def bootstrap_sum(
    values: Sequence[float],
    *,
    resamples: int,
    generator: np.random.Generator,
    chunk_size: int = 100,
) -> FloatArray:
    """Bootstrap a sum by resampling evidence units with replacement."""
    if resamples <= 0:
        msg = "resamples must be positive"
        raise ValueError(msg)
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        msg = "values must be one-dimensional"
        raise ValueError(msg)
    if len(array) == 0:
        return np.zeros(resamples, dtype=np.float64)
    output = np.empty(resamples, dtype=np.float64)
    for start in range(0, resamples, chunk_size):
        stop = min(start + chunk_size, resamples)
        indices = generator.integers(
            0,
            len(array),
            size=(stop - start, len(array)),
        )
        output[start:stop] = np.sum(array[indices], axis=1)
    return output


def percentile_interval(
    samples: Sequence[float] | FloatArray,
    point_estimate: float | None,
    *,
    confidence: float = 0.90,
) -> tuple[float | None, float | None]:
    """Return a percentile interval, expanded only if needed to contain its point."""
    if point_estimate is None or not math.isfinite(point_estimate):
        return None, None
    if not 0.0 < confidence < 1.0:
        msg = "confidence must be between zero and one"
        raise ValueError(msg)
    array = np.asarray(samples, dtype=np.float64)
    finite = array[np.isfinite(array)]
    if len(finite) == 0:
        return None, None
    tail = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(finite, [tail, 1.0 - tail])
    return min(float(lower), point_estimate), max(float(upper), point_estimate)


def cumulative_delta(
    previous: tuple[int, int] | None,
    current: tuple[int, int],
) -> tuple[int, int] | None:
    """Return monotone play/listener deltas; exclude first or corrected observations."""
    if previous is None:
        return None
    previous_playcount, previous_listeners = previous
    current_playcount, current_listeners = current
    if (
        current_playcount < previous_playcount
        or current_listeners < previous_listeners
    ):
        return None
    return (
        current_playcount - previous_playcount,
        current_listeners - previous_listeners,
    )


def opportunity_score(demand: float, supply: float) -> float:
    """Demand minus supply; swapping the arguments negates the score."""
    return demand - supply


def ewma(values: Sequence[float | None], *, halflife: float = 3.0) -> FloatArray:
    """Exponentially weighted mean that keeps missing weeks explicitly missing."""
    if halflife <= 0:
        msg = "halflife must be positive"
        raise ValueError(msg)
    alpha = 1.0 - math.exp(math.log(0.5) / halflife)
    result = np.full(len(values), np.nan, dtype=np.float64)
    state: float | None = None
    for index, value in enumerate(values):
        if value is None or not math.isfinite(value):
            continue
        state = value if state is None else alpha * value + (1.0 - alpha) * state
        result[index] = state
    return result


def shannon_entropy(values: Sequence[float]) -> float:
    """Shannon entropy of non-negative shares, using natural logarithms."""
    shares = _normalized_positive(values)
    if len(shares) == 0:
        return 0.0
    positive = shares[shares > 0]
    return float(-np.sum(positive * np.log(positive)))


def hhi(values: Sequence[float]) -> float:
    """Herfindahl-Hirschman concentration over non-negative values."""
    shares = _normalized_positive(values)
    return float(np.sum(np.square(shares))) if len(shares) else 0.0


def top_k_share(values: Sequence[float], *, k: int) -> float:
    """Share owned by the largest ``k`` non-negative observations."""
    if k <= 0:
        msg = "k must be positive"
        raise ValueError(msg)
    shares = _normalized_positive(values)
    if len(shares) == 0:
        return 0.0
    return float(np.sum(np.sort(shares)[-k:]))


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    """Jaccard similarity, undefined empty-vs-empty treated as one."""
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _normalized_positive(values: Sequence[float]) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or np.any(array < 0):
        msg = "values must be a one-dimensional non-negative sequence"
        raise ValueError(msg)
    total = float(np.sum(array))
    if total <= _EPSILON:
        return np.asarray([], dtype=np.float64)
    return array / total
