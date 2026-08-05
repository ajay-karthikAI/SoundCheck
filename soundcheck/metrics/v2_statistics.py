"""Hierarchical and peer-context statistical primitives for taxonomy v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from soundcheck.metrics.statistics import (
    beta_binomial_shrink,
    gamma_poisson_shrink,
    within_week_zscores,
)

FloatArray = npt.NDArray[np.float64]
_EPSILON = 1e-12
_MAX_PRIOR_CONCENTRATION = 1_000_000.0


@dataclass(frozen=True, slots=True)
class HierarchicalBetaResult:
    """Family and subgenre posterior shares for one ISO week."""

    posterior_counts: FloatArray
    posterior_shares: FloatArray
    observed_family_shares: FloatArray
    posterior_family_shares: FloatArray
    observed_conditional_shares: FloatArray
    posterior_conditional_shares: FloatArray
    global_prior_genre_shares: FloatArray
    family_prior_genre_shares: FloatArray
    subgenre_shrinkage_weights: FloatArray
    family_shrinkage_weights: FloatArray
    combined_shrinkage_weights: FloatArray


@dataclass(frozen=True, slots=True)
class HierarchicalGammaPoissonResult:
    """Genre supply rates shrunk through family means to a global mean."""

    posterior_rates: FloatArray
    family_prior_means: FloatArray
    global_prior_mean: float
    subgenre_shrinkage_weights: FloatArray
    family_shrinkage_weights: FloatArray
    combined_shrinkage_weights: FloatArray


def _validate_hierarchy_inputs(
    values: Sequence[float] | FloatArray,
    family_ids: Sequence[str],
) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or len(array) == 0:
        raise ValueError("values must be a non-empty one-dimensional sequence")
    if len(array) != len(family_ids):
        raise ValueError("values and family_ids must have equal length")
    if np.any(~np.isfinite(array)) or np.any(array < 0):
        raise ValueError("hierarchical inputs must be finite and non-negative")
    if any(not family_id for family_id in family_ids):
        raise ValueError("family IDs cannot be blank")
    return array


def hierarchical_beta_binomial_shrink(
    counts: Sequence[float] | FloatArray,
    family_ids: Sequence[str],
) -> HierarchicalBetaResult:
    """Shrink genre shares to a family prior, then families to a global prior."""
    values = _validate_hierarchy_inputs(counts, family_ids)
    families = tuple(sorted(set(family_ids)))
    indices_by_family = {
        family: np.asarray(
            [index for index, value in enumerate(family_ids) if value == family],
            dtype=np.int64,
        )
        for family in families
    }
    family_totals = np.asarray(
        [float(np.sum(values[indices_by_family[family]])) for family in families],
        dtype=np.float64,
    )
    family_fit = beta_binomial_shrink(family_totals)
    total = float(np.sum(values))
    posterior_shares = np.zeros(len(values), dtype=np.float64)
    observed_family = np.zeros(len(values), dtype=np.float64)
    posterior_family = np.zeros(len(values), dtype=np.float64)
    observed_conditional = np.zeros(len(values), dtype=np.float64)
    posterior_conditional = np.zeros(len(values), dtype=np.float64)
    global_prior = np.zeros(len(values), dtype=np.float64)
    family_prior = np.zeros(len(values), dtype=np.float64)
    subgenre_weight = np.zeros(len(values), dtype=np.float64)
    family_weight = np.full(
        len(values),
        family_fit.shrinkage_weight,
        dtype=np.float64,
    )

    for family_index, family in enumerate(families):
        indices = indices_by_family[family]
        local_fit = beta_binomial_shrink(values[indices])
        posterior_shares[indices] = (
            family_fit.posterior_shares[family_index]
            * local_fit.posterior_shares
        )
        observed_family[indices] = family_fit.observed_shares[family_index]
        posterior_family[indices] = family_fit.posterior_shares[family_index]
        observed_conditional[indices] = local_fit.observed_shares
        posterior_conditional[indices] = local_fit.posterior_shares
        global_prior[indices] = 1.0 / len(families) / len(indices)
        family_prior[indices] = (
            family_fit.posterior_shares[family_index] / len(indices)
        )
        subgenre_weight[indices] = local_fit.shrinkage_weight

    combined = 1.0 - (1.0 - subgenre_weight) * (1.0 - family_weight)
    return HierarchicalBetaResult(
        posterior_counts=posterior_shares * total,
        posterior_shares=posterior_shares,
        observed_family_shares=observed_family,
        posterior_family_shares=posterior_family,
        observed_conditional_shares=observed_conditional,
        posterior_conditional_shares=posterior_conditional,
        global_prior_genre_shares=global_prior,
        family_prior_genre_shares=family_prior,
        subgenre_shrinkage_weights=subgenre_weight,
        family_shrinkage_weights=family_weight,
        combined_shrinkage_weights=combined,
    )


def hierarchical_gamma_poisson_shrink(
    counts: Sequence[float] | FloatArray,
    family_ids: Sequence[str],
) -> HierarchicalGammaPoissonResult:
    """Shrink genre supply to family rates and family rates to the weekly global."""
    values = _validate_hierarchy_inputs(counts, family_ids)
    families = tuple(sorted(set(family_ids)))
    indices_by_family = {
        family: np.asarray(
            [index for index, value in enumerate(family_ids) if value == family],
            dtype=np.int64,
        )
        for family in families
    }
    family_rates = np.asarray(
        [
            float(np.mean(values[indices_by_family[family]]))
            for family in families
        ],
        dtype=np.float64,
    )
    family_fit = gamma_poisson_shrink(family_rates)
    posterior = np.zeros(len(values), dtype=np.float64)
    family_prior = np.zeros(len(values), dtype=np.float64)
    subgenre_weight = np.zeros(len(values), dtype=np.float64)
    family_weight = np.full(
        len(values),
        family_fit.shrinkage_weight,
        dtype=np.float64,
    )
    for family_index, family in enumerate(families):
        indices = indices_by_family[family]
        prior_mean = float(family_fit.posterior_rates[family_index])
        family_prior[indices] = prior_mean
        if prior_mean <= _EPSILON:
            posterior[indices] = 0.0
            subgenre_weight[indices] = 1.0
            continue
        variance = float(np.var(values[indices], ddof=0))
        if variance > prior_mean + _EPSILON:
            shape = prior_mean**2 / (variance - prior_mean)
        else:
            shape = _MAX_PRIOR_CONCENTRATION
        shape = min(max(shape, _EPSILON), _MAX_PRIOR_CONCENTRATION)
        rate = shape / prior_mean
        posterior[indices] = (values[indices] + shape) / (rate + 1.0)
        subgenre_weight[indices] = rate / (rate + 1.0)
    combined = 1.0 - (1.0 - subgenre_weight) * (1.0 - family_weight)
    return HierarchicalGammaPoissonResult(
        posterior_rates=posterior,
        family_prior_means=family_prior,
        global_prior_mean=family_fit.prior_mean,
        subgenre_shrinkage_weights=subgenre_weight,
        family_shrinkage_weights=family_weight,
        combined_shrinkage_weights=combined,
    )


def within_peer_family_zscores(
    values: Sequence[float | None],
    family_ids: Sequence[str],
) -> FloatArray:
    """Compute independent within-week z-scores inside each macro family."""
    if len(values) != len(family_ids):
        raise ValueError("values and family_ids must have equal length")
    result = np.full(len(values), np.nan, dtype=np.float64)
    for family in sorted(set(family_ids)):
        indices = [
            index
            for index, family_id in enumerate(family_ids)
            if family_id == family
        ]
        family_scores = within_week_zscores([values[index] for index in indices])
        result[indices] = family_scores
    return result


def kish_effective_n(weights: Sequence[float]) -> float:
    """Return Kish effective sample size for positive evidence weights."""
    array = np.asarray(weights, dtype=np.float64)
    if array.ndim != 1 or np.any(array < 0) or np.any(~np.isfinite(array)):
        raise ValueError("weights must be one-dimensional, finite, and non-negative")
    total = float(np.sum(array))
    squared = float(np.sum(np.square(array)))
    if total <= _EPSILON or squared <= _EPSILON:
        return 0.0
    return total**2 / squared
