"""Property tests for Phase 4 statistical invariants."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from soundcheck.metrics.statistics import (
    beta_binomial_shrink,
    cumulative_delta,
    gamma_poisson_shrink,
    opportunity_score,
    percentile_interval,
    shannon_entropy,
    within_week_zscores,
)


@given(
    st.lists(
        st.integers(min_value=0, max_value=100_000),
        min_size=2,
        max_size=20,
    )
)
def test_beta_binomial_shrinkage_moves_toward_prior_without_overshoot(
    counts: list[int],
) -> None:
    assume(sum(counts) > 0)
    result = beta_binomial_shrink([float(value) for value in counts])
    for observed, posterior in zip(
        result.observed_shares,
        result.posterior_shares,
        strict=True,
    ):
        lower = min(float(observed), result.prior_mean)
        upper = max(float(observed), result.prior_mean)
        assert lower - 1e-12 <= posterior <= upper + 1e-12


@given(
    st.lists(
        st.integers(min_value=0, max_value=10_000),
        min_size=2,
        max_size=20,
    )
)
def test_gamma_poisson_shrinkage_moves_toward_prior_without_overshoot(
    counts: list[int],
) -> None:
    result = gamma_poisson_shrink([float(value) for value in counts])
    for observed, posterior in zip(
        counts,
        result.posterior_rates,
        strict=True,
    ):
        lower = min(float(observed), result.prior_mean)
        upper = max(float(observed), result.prior_mean)
        assert lower - 1e-12 <= posterior <= upper + 1e-12


@given(
    st.lists(
        st.floats(
            min_value=-1_000_000,
            max_value=1_000_000,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=100,
    )
)
def test_within_week_zscores_sum_to_zero(values: list[float]) -> None:
    scores = within_week_zscores(values)
    assert math.fsum(float(value) for value in scores) == pytest.approx(
        0.0,
        abs=1e-7,
    )


@given(
    st.lists(
        st.floats(
            min_value=-1_000_000,
            max_value=1_000_000,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=100,
    ),
    st.floats(
        min_value=-1_000_000,
        max_value=1_000_000,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_percentile_intervals_contain_point_estimate(
    samples: list[float],
    point: float,
) -> None:
    lower, upper = percentile_interval(samples, point)
    assert lower is not None
    assert upper is not None
    assert lower <= point <= upper


@given(
    st.floats(
        min_value=-1_000,
        max_value=1_000,
        allow_nan=False,
        allow_infinity=False,
    ),
    st.floats(
        min_value=-1_000,
        max_value=1_000,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_opportunity_flips_sign_when_demand_and_supply_swap(
    demand: float,
    supply: float,
) -> None:
    assert opportunity_score(demand, supply) == pytest.approx(
        -opportunity_score(supply, demand)
    )


@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=0, max_value=1_000_000),
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=10_000),
            st.integers(min_value=0, max_value=10_000),
        ),
        min_size=1,
        max_size=30,
    ),
)
def test_monotone_cumulative_sequences_have_nonnegative_deltas(
    starting_playcount: int,
    starting_listeners: int,
    increments: list[tuple[int, int]],
) -> None:
    previous = (starting_playcount, starting_listeners)
    for playcount_increment, listener_increment in increments:
        current = (
            previous[0] + playcount_increment,
            previous[1] + listener_increment,
        )
        delta = cumulative_delta(previous, current)
        assert delta is not None
        assert delta[0] >= 0
        assert delta[1] >= 0
        previous = current


@given(st.integers(min_value=1, max_value=100))
def test_entropy_is_maximal_for_uniform_and_zero_for_single_genre(
    genre_count: int,
) -> None:
    uniform = [1.0] * genre_count
    concentrated = [1.0] + [0.0] * (genre_count - 1)
    assert shannon_entropy(uniform) == pytest.approx(math.log(genre_count))
    assert shannon_entropy(concentrated) == pytest.approx(0.0)
    random_values = np.arange(1, genre_count + 1, dtype=np.float64)
    assert shannon_entropy(random_values.tolist()) <= math.log(genre_count) + 1e-12
