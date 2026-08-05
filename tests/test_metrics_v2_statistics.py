"""Property tests for taxonomy-v2 hierarchical and peer contexts."""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from soundcheck.metrics.statistics import (
    cumulative_delta,
    percentile_interval,
    within_week_zscores,
)
from soundcheck.metrics.v2_statistics import (
    hierarchical_beta_binomial_shrink,
    hierarchical_gamma_poisson_shrink,
    within_peer_family_zscores,
)


@given(
    st.lists(
        st.integers(min_value=0, max_value=100_000),
        min_size=4,
        max_size=20,
    ).filter(lambda values: len(values) % 2 == 0)
)
def test_hierarchical_conversation_shrinkage_moves_toward_each_prior(
    counts: list[int],
) -> None:
    assume(sum(counts) > 0)
    half = len(counts) // 2
    families = ("family_a",) * half + ("family_b",) * half
    result = hierarchical_beta_binomial_shrink(
        [float(value) for value in counts],
        families,
    )
    for observed, posterior, prior in zip(
        result.observed_conditional_shares,
        result.posterior_conditional_shares,
        [1.0 / half] * len(counts),
        strict=True,
    ):
        assert min(observed, prior) - 1e-12 <= posterior
        assert posterior <= max(observed, prior) + 1e-12
    for observed, posterior in zip(
        result.observed_family_shares,
        result.posterior_family_shares,
        strict=True,
    ):
        assert min(observed, 0.5) - 1e-12 <= posterior
        assert posterior <= max(observed, 0.5) + 1e-12
    assert float(np.sum(result.posterior_shares)) == pytest.approx(1.0)


@given(
    st.lists(
        st.integers(min_value=0, max_value=10_000),
        min_size=4,
        max_size=20,
    ).filter(lambda values: len(values) % 2 == 0)
)
def test_hierarchical_supply_posterior_stays_between_genre_and_family_prior(
    counts: list[int],
) -> None:
    half = len(counts) // 2
    families = ("family_a",) * half + ("family_b",) * half
    result = hierarchical_gamma_poisson_shrink(
        [float(value) for value in counts],
        families,
    )
    for observed, posterior, family_prior in zip(
        counts,
        result.posterior_rates,
        result.family_prior_means,
        strict=True,
    ):
        assert min(observed, family_prior) - 1e-12 <= posterior
        assert posterior <= max(observed, family_prior) + 1e-12


@given(
    st.lists(
        st.floats(
            min_value=-1_000_000,
            max_value=1_000_000,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=4,
        max_size=40,
    ).filter(lambda values: len(values) % 2 == 0)
)
def test_within_family_zscores_sum_to_zero(values: list[float]) -> None:
    half = len(values) // 2
    families = ("family_a",) * half + ("family_b",) * half
    scores = within_peer_family_zscores(values, families)
    assert math.fsum(float(value) for value in scores[:half]) == pytest.approx(
        0.0,
        abs=1e-7,
    )
    assert math.fsum(float(value) for value in scores[half:]) == pytest.approx(
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
    )
)
def test_v2_global_within_week_zscores_sum_to_zero(
    values: list[float],
) -> None:
    scores = within_week_zscores(values)
    assert math.fsum(float(value) for value in scores) == pytest.approx(
        0.0,
        abs=1e-7,
    )


@given(
    st.lists(
        st.floats(
            min_value=-1_000,
            max_value=1_000,
            allow_nan=False,
            allow_infinity=False,
        ),
        min_size=1,
        max_size=100,
    ),
    st.floats(
        min_value=-1_000,
        max_value=1_000,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_v2_uncertainty_intervals_contain_points(
    samples: list[float],
    point: float,
) -> None:
    low, high = percentile_interval(samples, point)
    assert low is not None
    assert high is not None
    assert low <= point <= high


def test_first_snapshot_and_negative_correction_never_form_listening_metrics() -> None:
    assert cumulative_delta(None, (100, 10)) is None
    assert cumulative_delta((100, 10), (99, 11)) is None
    assert cumulative_delta((100, 10), (101, 9)) is None


@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=0, max_value=100_000),
    st.integers(min_value=0, max_value=100_000),
)
def test_monotone_cumulative_deltas_are_never_negative(
    playcount: int,
    listeners: int,
    playcount_increment: int,
    listener_increment: int,
) -> None:
    delta = cumulative_delta(
        (playcount, listeners),
        (
            playcount + playcount_increment,
            listeners + listener_increment,
        ),
    )
    assert delta is not None
    assert delta[0] >= 0
    assert delta[1] >= 0
