"""Evidence-first weekly metric construction and uncertainty propagation."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np
import numpy.typing as npt

from soundcheck.metrics.models import (
    EcosystemWeekMetric,
    GenreWeekMetric,
    MetricEvidence,
    MetricsBatch,
)
from soundcheck.metrics.statistics import (
    beta_binomial_shrink,
    bootstrap_sum,
    cumulative_delta,
    ewma,
    gamma_poisson_shrink,
    hhi,
    jaccard_similarity,
    percentile_interval,
    shannon_entropy,
    top_k_share,
    within_week_zscores,
)

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
type CellKey = tuple[date, str]
type ArtistCellKey = tuple[date, str, str]

DEFAULT_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_BOOTSTRAP_SEED = 20_260_723
TREND_HALFLIFE_WEEKS = 3.0
SPIKE_STANDARD_DEVIATIONS = 2.5


@dataclass(slots=True)
class _ConversationCell:
    mentions: int = 0
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    scores: list[float] = field(default_factory=list)
    post_uris: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _ListeningCell:
    playcount_delta: int = 0
    listeners_delta: int = 0
    scores: list[float] = field(default_factory=list)
    artist_keys: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _SupplyCell:
    release_group_mbids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _MetricArrays:
    weeks: tuple[date, ...]
    genres: tuple[str, ...]
    conversation_raw: FloatArray
    conversation_shrunk: FloatArray
    conversation_share_raw: FloatArray
    conversation_share_shrunk: FloatArray
    conversation_prior_share: FloatArray
    conversation_effective_n: FloatArray
    conversation_shrinkage_weight: FloatArray
    listening_raw: FloatArray
    listening_playcount_delta: FloatArray
    listening_listeners_delta: FloatArray
    supply_raw: FloatArray
    supply_shrunk: FloatArray
    supply_prior_mean: FloatArray
    supply_effective_n: FloatArray
    supply_shrinkage_weight: FloatArray
    conversation_index: FloatArray
    listening_index: FloatArray
    supply_index: FloatArray
    opportunity: FloatArray
    discovery_gap: FloatArray
    conversation_bootstrap_raw: FloatArray
    listening_bootstrap_raw: FloatArray
    supply_bootstrap_raw: FloatArray
    conversation_index_bootstrap: FloatArray
    listening_index_bootstrap: FloatArray
    supply_index_bootstrap: FloatArray
    opportunity_bootstrap: FloatArray
    discovery_gap_bootstrap: FloatArray


@dataclass(frozen=True, slots=True)
class _TrendArrays:
    conversation_ewma: FloatArray
    listening_ewma: FloatArray
    supply_ewma: FloatArray
    conversation_ewma_bootstrap: FloatArray
    listening_ewma_bootstrap: FloatArray
    supply_ewma_bootstrap: FloatArray
    conversation_spike: BoolArray
    listening_spike: BoolArray
    supply_spike: BoolArray


def build_metrics(
    evidence: MetricEvidence,
    canonical_genres: tuple[str, ...],
    *,
    computed_at: datetime | None = None,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> MetricsBatch:
    """Build all genre and ecosystem marts from immutable evidence."""
    genres = tuple(dict.fromkeys(genre.strip().casefold() for genre in canonical_genres))
    if not genres or any(not genre for genre in genres):
        msg = "canonical genres must be non-empty"
        raise ValueError(msg)
    if len(genres) != len(canonical_genres):
        msg = "canonical genres must be unique after normalization"
        raise ValueError(msg)
    if bootstrap_resamples <= 0:
        msg = "bootstrap_resamples must be positive"
        raise ValueError(msg)
    metric_time = computed_at or datetime.now(UTC)
    if metric_time.tzinfo is None:
        msg = "computed_at must include a timezone"
        raise ValueError(msg)
    metric_time = metric_time.astimezone(UTC)

    conversation_cells = _aggregate_conversation(evidence)
    listening_cells = _aggregate_listening(evidence)
    supply_cells = _aggregate_supply(evidence)
    weeks = tuple(
        sorted(
            {
                week
                for week, _genre in (
                    set(conversation_cells) | set(listening_cells) | set(supply_cells)
                )
            }
        )
    )
    if not weeks:
        return MetricsBatch(genre_weeks=(), ecosystem_weeks=())

    arrays = _calculate_arrays(
        weeks,
        genres,
        conversation_cells,
        listening_cells,
        supply_cells,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    trend_values = _calculate_trends(arrays)
    breakout_flags = _breakout_flags(
        arrays.conversation_index,
        arrays.listening_index,
    )
    genre_rows = _build_genre_rows(
        arrays,
        trend_values,
        breakout_flags,
        conversation_cells,
        listening_cells,
        supply_cells,
        metric_time,
    )
    ecosystem_rows = _build_ecosystem_rows(
        arrays,
        breakout_flags,
        metric_time,
    )
    return MetricsBatch(
        genre_weeks=genre_rows,
        ecosystem_weeks=ecosystem_rows,
    )


def _aggregate_conversation(
    evidence: MetricEvidence,
) -> dict[CellKey, _ConversationCell]:
    cells: dict[CellKey, _ConversationCell] = defaultdict(_ConversationCell)
    for item in evidence.conversation:
        cell = cells[(item.week_start, item.canonical_genre.casefold())]
        cell.mentions += item.mentions
        cell.likes += item.likes
        cell.reposts += item.reposts
        cell.replies += item.replies
        cell.scores.append(item.weighted_score)
        cell.post_uris.add(item.post_uri)
    return dict(cells)


def _aggregate_listening(
    evidence: MetricEvidence,
) -> dict[CellKey, _ListeningCell]:
    artist_deltas: dict[ArtistCellKey, list[int]] = defaultdict(lambda: [0, 0])
    for item in evidence.listening_candidates:
        previous = (
            None
            if item.previous_playcount is None or item.previous_listeners is None
            else (item.previous_playcount, item.previous_listeners)
        )
        delta = cumulative_delta(
            previous,
            (item.playcount, item.listeners),
        )
        if delta is None:
            continue
        aggregate = artist_deltas[
            (
                item.week_start,
                item.canonical_genre.casefold(),
                item.artist_key,
            )
        ]
        aggregate[0] += delta[0]
        aggregate[1] += delta[1]

    cells: dict[CellKey, _ListeningCell] = defaultdict(_ListeningCell)
    for (week, genre, artist_key), (playcount_delta, listeners_delta) in (
        artist_deltas.items()
    ):
        cell = cells[(week, genre)]
        cell.playcount_delta += playcount_delta
        cell.listeners_delta += listeners_delta
        cell.scores.append(float(playcount_delta + 5 * listeners_delta))
        cell.artist_keys.add(artist_key)
    return dict(cells)


def _aggregate_supply(evidence: MetricEvidence) -> dict[CellKey, _SupplyCell]:
    cells: dict[CellKey, _SupplyCell] = defaultdict(_SupplyCell)
    for item in evidence.supply:
        cells[(item.week_start, item.canonical_genre.casefold())].release_group_mbids.add(
            item.release_group_mbid
        )
    return dict(cells)


def _calculate_arrays(
    weeks: tuple[date, ...],
    genres: tuple[str, ...],
    conversation_cells: dict[CellKey, _ConversationCell],
    listening_cells: dict[CellKey, _ListeningCell],
    supply_cells: dict[CellKey, _SupplyCell],
    *,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> _MetricArrays:
    week_count = len(weeks)
    genre_count = len(genres)
    shape = (week_count, genre_count)
    conversation_raw = np.zeros(shape, dtype=np.float64)
    listening_raw = np.full(shape, np.nan, dtype=np.float64)
    listening_playcount = np.full(shape, np.nan, dtype=np.float64)
    listening_listeners = np.full(shape, np.nan, dtype=np.float64)
    supply_raw = np.zeros(shape, dtype=np.float64)
    conversation_bootstrap_raw = np.zeros(
        (week_count, bootstrap_resamples, genre_count),
        dtype=np.float64,
    )
    listening_bootstrap_raw = np.full(
        (week_count, bootstrap_resamples, genre_count),
        np.nan,
        dtype=np.float64,
    )
    supply_bootstrap_raw = np.zeros(
        (week_count, bootstrap_resamples, genre_count),
        dtype=np.float64,
    )
    generator = np.random.default_rng(bootstrap_seed)

    for week_index, week in enumerate(weeks):
        for genre_index, genre in enumerate(genres):
            key = (week, genre)
            conversation = conversation_cells.get(key)
            if conversation is not None:
                conversation_raw[week_index, genre_index] = sum(conversation.scores)
                conversation_bootstrap_raw[week_index, :, genre_index] = bootstrap_sum(
                    conversation.scores,
                    resamples=bootstrap_resamples,
                    generator=generator,
                )
            listening = listening_cells.get(key)
            if listening is not None:
                listening_raw[week_index, genre_index] = sum(listening.scores)
                listening_playcount[week_index, genre_index] = listening.playcount_delta
                listening_listeners[week_index, genre_index] = listening.listeners_delta
                listening_bootstrap_raw[week_index, :, genre_index] = bootstrap_sum(
                    listening.scores,
                    resamples=bootstrap_resamples,
                    generator=generator,
                )
            supply = supply_cells.get(key)
            if supply is not None:
                release_values = [1.0] * len(supply.release_group_mbids)
                supply_raw[week_index, genre_index] = len(release_values)
                supply_bootstrap_raw[week_index, :, genre_index] = bootstrap_sum(
                    release_values,
                    resamples=bootstrap_resamples,
                    generator=generator,
                )

    conversation_shrunk = np.zeros(shape, dtype=np.float64)
    conversation_share_raw = np.zeros(shape, dtype=np.float64)
    conversation_share_shrunk = np.zeros(shape, dtype=np.float64)
    conversation_prior_share = np.zeros(shape, dtype=np.float64)
    conversation_effective_n = np.zeros(shape, dtype=np.float64)
    conversation_shrinkage_weight = np.zeros(shape, dtype=np.float64)
    supply_shrunk = np.zeros(shape, dtype=np.float64)
    supply_prior_mean = np.zeros(shape, dtype=np.float64)
    supply_effective_n = np.zeros(shape, dtype=np.float64)
    supply_shrinkage_weight = np.zeros(shape, dtype=np.float64)
    conversation_index = np.zeros(shape, dtype=np.float64)
    listening_index = np.full(shape, np.nan, dtype=np.float64)
    supply_index = np.zeros(shape, dtype=np.float64)

    conversation_index_bootstrap = np.empty_like(conversation_bootstrap_raw)
    listening_index_bootstrap = np.full_like(listening_bootstrap_raw, np.nan)
    supply_index_bootstrap = np.empty_like(supply_bootstrap_raw)

    for week_index in range(week_count):
        conversation_fit = beta_binomial_shrink(
            conversation_raw[week_index, :] * 2.0
        )
        conversation_shrunk[week_index, :] = (
            conversation_fit.posterior_counts / 2.0
        )
        conversation_share_raw[week_index, :] = conversation_fit.observed_shares
        conversation_share_shrunk[week_index, :] = (
            conversation_fit.posterior_shares
        )
        conversation_prior_share[week_index, :] = conversation_fit.prior_mean
        conversation_effective_n[week_index, :] = (
            conversation_fit.effective_n / 2.0
        )
        conversation_shrinkage_weight[week_index, :] = (
            conversation_fit.shrinkage_weight
        )
        supply_fit = gamma_poisson_shrink(supply_raw[week_index, :])
        supply_shrunk[week_index, :] = supply_fit.posterior_rates
        supply_prior_mean[week_index, :] = supply_fit.prior_mean
        supply_effective_n[week_index, :] = supply_fit.effective_n
        supply_shrinkage_weight[week_index, :] = supply_fit.shrinkage_weight

        conversation_index[week_index, :] = within_week_zscores(
            np.log1p(conversation_shrunk[week_index, :]).tolist()
        )
        listening_index[week_index, :] = within_week_zscores(
            [
                None if not math.isfinite(value) else math.log1p(value)
                for value in listening_raw[week_index, :]
            ]
        )
        supply_index[week_index, :] = within_week_zscores(
            np.log1p(supply_shrunk[week_index, :]).tolist()
        )

        for sample_index in range(bootstrap_resamples):
            conversation_sample = beta_binomial_shrink(
                conversation_bootstrap_raw[week_index, sample_index, :] * 2.0
            )
            conversation_index_bootstrap[
                week_index, sample_index, :
            ] = within_week_zscores(
                np.log1p(conversation_sample.posterior_counts / 2.0).tolist()
            )
            supply_sample = gamma_poisson_shrink(
                supply_bootstrap_raw[week_index, sample_index, :]
            )
            supply_index_bootstrap[
                week_index, sample_index, :
            ] = within_week_zscores(
                np.log1p(supply_sample.posterior_rates).tolist()
            )
            listening_index_bootstrap[
                week_index, sample_index, :
            ] = within_week_zscores(
                [
                    None if not math.isfinite(value) else math.log1p(value)
                    for value in listening_bootstrap_raw[
                        week_index, sample_index, :
                    ]
                ]
            )

    demand = (conversation_index + listening_index) / 2.0
    opportunity = demand - supply_index
    discovery_gap = listening_index - conversation_index
    opportunity_bootstrap = (
        (conversation_index_bootstrap + listening_index_bootstrap) / 2.0
        - supply_index_bootstrap
    )
    discovery_gap_bootstrap = (
        listening_index_bootstrap - conversation_index_bootstrap
    )
    return _MetricArrays(
        weeks=weeks,
        genres=genres,
        conversation_raw=conversation_raw,
        conversation_shrunk=conversation_shrunk,
        conversation_share_raw=conversation_share_raw,
        conversation_share_shrunk=conversation_share_shrunk,
        conversation_prior_share=conversation_prior_share,
        conversation_effective_n=conversation_effective_n,
        conversation_shrinkage_weight=conversation_shrinkage_weight,
        listening_raw=listening_raw,
        listening_playcount_delta=listening_playcount,
        listening_listeners_delta=listening_listeners,
        supply_raw=supply_raw,
        supply_shrunk=supply_shrunk,
        supply_prior_mean=supply_prior_mean,
        supply_effective_n=supply_effective_n,
        supply_shrinkage_weight=supply_shrinkage_weight,
        conversation_index=conversation_index,
        listening_index=listening_index,
        supply_index=supply_index,
        opportunity=opportunity,
        discovery_gap=discovery_gap,
        conversation_bootstrap_raw=conversation_bootstrap_raw,
        listening_bootstrap_raw=listening_bootstrap_raw,
        supply_bootstrap_raw=supply_bootstrap_raw,
        conversation_index_bootstrap=conversation_index_bootstrap,
        listening_index_bootstrap=listening_index_bootstrap,
        supply_index_bootstrap=supply_index_bootstrap,
        opportunity_bootstrap=opportunity_bootstrap,
        discovery_gap_bootstrap=discovery_gap_bootstrap,
    )


def _calculate_trends(
    arrays: _MetricArrays,
) -> _TrendArrays:
    conversation_ewma = _ewma_matrix(arrays.conversation_index)
    listening_ewma = _ewma_matrix(arrays.listening_index)
    supply_ewma = _ewma_matrix(arrays.supply_index)
    conversation_ewma_bootstrap = _ewma_bootstrap(
        arrays.conversation_index_bootstrap
    )
    listening_ewma_bootstrap = _ewma_bootstrap(arrays.listening_index_bootstrap)
    supply_ewma_bootstrap = _ewma_bootstrap(arrays.supply_index_bootstrap)
    return _TrendArrays(
        conversation_ewma=conversation_ewma,
        listening_ewma=listening_ewma,
        supply_ewma=supply_ewma,
        conversation_ewma_bootstrap=conversation_ewma_bootstrap,
        listening_ewma_bootstrap=listening_ewma_bootstrap,
        supply_ewma_bootstrap=supply_ewma_bootstrap,
        conversation_spike=_spike_flags(
            arrays.conversation_index,
            conversation_ewma,
        ),
        listening_spike=_spike_flags(
            arrays.listening_index,
            listening_ewma,
        ),
        supply_spike=_spike_flags(arrays.supply_index, supply_ewma),
    )


def _ewma_matrix(values: FloatArray) -> FloatArray:
    result = np.full_like(values, np.nan)
    for genre_index in range(values.shape[1]):
        result[:, genre_index] = ewma(
            [
                None if not math.isfinite(value) else float(value)
                for value in values[:, genre_index]
            ],
            halflife=TREND_HALFLIFE_WEEKS,
        )
    return result


def _ewma_bootstrap(values: FloatArray) -> FloatArray:
    result = np.full_like(values, np.nan)
    state = np.full(values.shape[1:], np.nan, dtype=np.float64)
    alpha = 1.0 - math.exp(math.log(0.5) / TREND_HALFLIFE_WEEKS)
    for week_index in range(values.shape[0]):
        current = values[week_index, :, :]
        observed = np.isfinite(current)
        new_state = observed & ~np.isfinite(state)
        continuing = observed & np.isfinite(state)
        state[new_state] = current[new_state]
        state[continuing] = (
            alpha * current[continuing] + (1.0 - alpha) * state[continuing]
        )
        result[week_index, :, :][observed] = state[observed]
    return result


def _spike_flags(values: FloatArray, baseline: FloatArray) -> BoolArray:
    flags = np.zeros(values.shape, dtype=np.bool_)
    for week_index in range(values.shape[0]):
        residual = values[week_index, :] - baseline[week_index, :]
        finite = residual[np.isfinite(residual)]
        if len(finite) < 2:
            continue
        pooled_standard_deviation = float(np.std(finite, ddof=0))
        if pooled_standard_deviation <= 1e-12:
            continue
        flags[week_index, :] = (
            residual > SPIKE_STANDARD_DEVIATIONS * pooled_standard_deviation
        )
    return flags


def _breakout_flags(
    conversation_index: FloatArray,
    listening_index: FloatArray,
) -> BoolArray:
    flags = np.zeros(conversation_index.shape, dtype=np.bool_)
    for week_index in range(conversation_index.shape[0]):
        observed = np.isfinite(listening_index[week_index, :])
        if not np.any(observed):
            continue
        listening_cutoff = float(
            np.quantile(listening_index[week_index, observed], 0.90)
        )
        conversation_median = float(
            np.median(conversation_index[week_index, :])
        )
        flags[week_index, :] = (
            observed
            & (listening_index[week_index, :] >= listening_cutoff)
            & (conversation_index[week_index, :] < conversation_median)
        )
    return flags


def _build_genre_rows(
    arrays: _MetricArrays,
    trends: _TrendArrays,
    breakout_flags: BoolArray,
    conversation_cells: dict[CellKey, _ConversationCell],
    listening_cells: dict[CellKey, _ListeningCell],
    supply_cells: dict[CellKey, _SupplyCell],
    computed_at: datetime,
) -> tuple[GenreWeekMetric, ...]:
    rows: list[GenreWeekMetric] = []
    for week_index, week in enumerate(arrays.weeks):
        iso = week.isocalendar()
        for genre_index, genre in enumerate(arrays.genres):
            key = (week, genre)
            conversation = conversation_cells.get(key, _ConversationCell())
            listening = listening_cells.get(key)
            supply = supply_cells.get(key, _SupplyCell())
            conversation_ci = _required_interval(
                arrays.conversation_index_bootstrap[
                    week_index, :, genre_index
                ],
                float(arrays.conversation_index[week_index, genre_index]),
            )
            supply_ci = _required_interval(
                arrays.supply_index_bootstrap[week_index, :, genre_index],
                float(arrays.supply_index[week_index, genre_index]),
            )
            listening_point = _optional_float(
                arrays.listening_index[week_index, genre_index]
            )
            opportunity_point = _optional_float(
                arrays.opportunity[week_index, genre_index]
            )
            discovery_gap_point = _optional_float(
                arrays.discovery_gap[week_index, genre_index]
            )
            listening_ci = percentile_interval(
                arrays.listening_index_bootstrap[
                    week_index, :, genre_index
                ],
                listening_point,
            )
            opportunity_ci = percentile_interval(
                arrays.opportunity_bootstrap[week_index, :, genre_index],
                opportunity_point,
            )
            discovery_gap_ci = percentile_interval(
                arrays.discovery_gap_bootstrap[week_index, :, genre_index],
                discovery_gap_point,
            )
            conversation_ewma_point = float(
                trends.conversation_ewma[week_index, genre_index]
            )
            listening_ewma_point = _optional_float(
                trends.listening_ewma[week_index, genre_index]
            )
            supply_ewma_point = float(
                trends.supply_ewma[week_index, genre_index]
            )
            conversation_ewma_ci = _required_interval(
                trends.conversation_ewma_bootstrap[
                    week_index, :, genre_index
                ],
                conversation_ewma_point,
            )
            listening_ewma_ci = percentile_interval(
                trends.listening_ewma_bootstrap[
                    week_index, :, genre_index
                ],
                listening_ewma_point,
            )
            supply_ewma_ci = _required_interval(
                trends.supply_ewma_bootstrap[week_index, :, genre_index],
                supply_ewma_point,
            )
            rows.append(
                GenreWeekMetric(
                    week_start=week,
                    iso_year=iso.year,
                    iso_week=iso.week,
                    canonical_genre=genre,
                    conversation_mentions=conversation.mentions,
                    conversation_likes=conversation.likes,
                    conversation_reposts=conversation.reposts,
                    conversation_replies=conversation.replies,
                    conversation_score_raw=float(
                        arrays.conversation_raw[week_index, genre_index]
                    ),
                    conversation_score_shrunk=float(
                        arrays.conversation_shrunk[week_index, genre_index]
                    ),
                    conversation_share_raw=float(
                        arrays.conversation_share_raw[week_index, genre_index]
                    ),
                    conversation_share_shrunk=float(
                        arrays.conversation_share_shrunk[week_index, genre_index]
                    ),
                    conversation_prior_share=float(
                        arrays.conversation_prior_share[week_index, genre_index]
                    ),
                    conversation_effective_n=float(
                        arrays.conversation_effective_n[week_index, genre_index]
                    ),
                    conversation_shrinkage_weight=float(
                        arrays.conversation_shrinkage_weight[
                            week_index, genre_index
                        ]
                    ),
                    listening_playcount_delta=(
                        None if listening is None else listening.playcount_delta
                    ),
                    listening_listeners_delta=(
                        None if listening is None else listening.listeners_delta
                    ),
                    listening_score_raw=_optional_float(
                        arrays.listening_raw[week_index, genre_index]
                    ),
                    supply_release_groups=len(supply.release_group_mbids),
                    supply_rate_shrunk=float(
                        arrays.supply_shrunk[week_index, genre_index]
                    ),
                    supply_prior_mean=float(
                        arrays.supply_prior_mean[week_index, genre_index]
                    ),
                    supply_effective_n=float(
                        arrays.supply_effective_n[week_index, genre_index]
                    ),
                    supply_shrinkage_weight=float(
                        arrays.supply_shrinkage_weight[week_index, genre_index]
                    ),
                    conversation_index=float(
                        arrays.conversation_index[week_index, genre_index]
                    ),
                    conversation_index_ci_low=conversation_ci[0],
                    conversation_index_ci_high=conversation_ci[1],
                    listening_index=listening_point,
                    listening_index_ci_low=listening_ci[0],
                    listening_index_ci_high=listening_ci[1],
                    supply_index=float(
                        arrays.supply_index[week_index, genre_index]
                    ),
                    supply_index_ci_low=supply_ci[0],
                    supply_index_ci_high=supply_ci[1],
                    opportunity=opportunity_point,
                    opportunity_ci_low=opportunity_ci[0],
                    opportunity_ci_high=opportunity_ci[1],
                    discovery_gap=discovery_gap_point,
                    discovery_gap_ci_low=discovery_gap_ci[0],
                    discovery_gap_ci_high=discovery_gap_ci[1],
                    conversation_ewma=conversation_ewma_point,
                    conversation_ewma_ci_low=conversation_ewma_ci[0],
                    conversation_ewma_ci_high=conversation_ewma_ci[1],
                    listening_ewma=listening_ewma_point,
                    listening_ewma_ci_low=listening_ewma_ci[0],
                    listening_ewma_ci_high=listening_ewma_ci[1],
                    supply_ewma=supply_ewma_point,
                    supply_ewma_ci_low=supply_ewma_ci[0],
                    supply_ewma_ci_high=supply_ewma_ci[1],
                    conversation_spike=bool(
                        trends.conversation_spike[week_index, genre_index]
                    ),
                    listening_spike=bool(
                        trends.listening_spike[week_index, genre_index]
                    ),
                    supply_spike=bool(
                        trends.supply_spike[week_index, genre_index]
                    ),
                    breakout_precursor=bool(
                        breakout_flags[week_index, genre_index]
                    ),
                    conversation_post_uris=tuple(sorted(conversation.post_uris)),
                    listening_artist_keys=(
                        () if listening is None else tuple(sorted(listening.artist_keys))
                    ),
                    supply_release_group_mbids=tuple(
                        sorted(supply.release_group_mbids)
                    ),
                    computed_at=computed_at,
                )
            )
    return tuple(rows)


def _build_ecosystem_rows(
    arrays: _MetricArrays,
    breakout_flags: BoolArray,
    computed_at: datetime,
) -> tuple[EcosystemWeekMetric, ...]:
    rows: list[EcosystemWeekMetric] = []
    index_by_week = {week: index for index, week in enumerate(arrays.weeks)}
    for week_index, week in enumerate(arrays.weeks):
        iso = week.isocalendar()
        listening_values = arrays.listening_raw[week_index, :]
        listening_observed = np.isfinite(listening_values)
        listening_total = float(np.nansum(listening_values))
        if np.any(listening_observed) and listening_total > 0.0:
            observed_listening = listening_values[listening_observed].tolist()
            entropy_point = shannon_entropy(observed_listening)
            effective_point = math.exp(entropy_point)
            top10_point = top_k_share(observed_listening, k=10)
            entropy_samples = np.full(
                arrays.listening_bootstrap_raw.shape[1],
                np.nan,
                dtype=np.float64,
            )
            effective_samples = np.full_like(entropy_samples, np.nan)
            top10_samples = np.full_like(entropy_samples, np.nan)
            for sample_index in range(len(entropy_samples)):
                sample = arrays.listening_bootstrap_raw[
                    week_index, sample_index, listening_observed
                ]
                if float(np.sum(sample)) <= 0.0:
                    continue
                entropy_samples[sample_index] = shannon_entropy(sample.tolist())
                effective_samples[sample_index] = math.exp(
                    entropy_samples[sample_index]
                )
                top10_samples[sample_index] = top_k_share(
                    sample.tolist(),
                    k=10,
                )
            entropy_ci = percentile_interval(entropy_samples, entropy_point)
            effective_ci = percentile_interval(effective_samples, effective_point)
            top10_ci = percentile_interval(top10_samples, top10_point)
        else:
            entropy_point = None
            effective_point = None
            top10_point = None
            entropy_ci = (None, None)
            effective_ci = (None, None)
            top10_ci = (None, None)

        conversation_values = arrays.conversation_raw[week_index, :]
        if float(np.sum(conversation_values)) > 0.0:
            hhi_point = hhi(conversation_values.tolist())
            hhi_samples = np.asarray(
                [
                    hhi(
                        arrays.conversation_bootstrap_raw[
                            week_index, sample_index, :
                        ].tolist()
                    )
                    for sample_index in range(
                        arrays.conversation_bootstrap_raw.shape[1]
                    )
                ],
                dtype=np.float64,
            )
            hhi_ci = percentile_interval(hhi_samples, hhi_point)
        else:
            hhi_point = None
            hhi_ci = (None, None)

        prior_index = index_by_week.get(week - timedelta(weeks=4))
        churn_point: float | None
        churn_ci: tuple[float | None, float | None]
        opportunity_observed = np.isfinite(arrays.opportunity[week_index, :])
        if prior_index is None or not np.any(opportunity_observed):
            churn_point = None
            churn_ci = (None, None)
        else:
            current_top = _top_genres(
                arrays.opportunity[week_index, :],
                arrays.genres,
                25,
            )
            previous_top = _top_genres(
                arrays.opportunity[prior_index, :],
                arrays.genres,
                25,
            )
            if not current_top or not previous_top:
                churn_point = None
                churn_ci = (None, None)
            else:
                churn_point = jaccard_similarity(current_top, previous_top)
                churn_samples = np.asarray(
                    [
                        jaccard_similarity(
                            _top_genres(
                                arrays.opportunity_bootstrap[
                                    week_index, sample_index, :
                                ],
                                arrays.genres,
                                25,
                            ),
                            _top_genres(
                                arrays.opportunity_bootstrap[
                                    prior_index, sample_index, :
                                ],
                                arrays.genres,
                                25,
                            ),
                        )
                        for sample_index in range(
                            arrays.opportunity_bootstrap.shape[1]
                        )
                    ],
                    dtype=np.float64,
                )
                churn_ci = percentile_interval(churn_samples, churn_point)

        breakout_genres = tuple(
            genre
            for genre_index, genre in enumerate(arrays.genres)
            if breakout_flags[week_index, genre_index]
        )
        rows.append(
            EcosystemWeekMetric(
                week_start=week,
                iso_year=iso.year,
                iso_week=iso.week,
                shannon_listening_entropy=entropy_point,
                shannon_listening_entropy_ci_low=entropy_ci[0],
                shannon_listening_entropy_ci_high=entropy_ci[1],
                effective_genres=effective_point,
                effective_genres_ci_low=effective_ci[0],
                effective_genres_ci_high=effective_ci[1],
                conversation_hhi=hhi_point,
                conversation_hhi_ci_low=hhi_ci[0],
                conversation_hhi_ci_high=hhi_ci[1],
                listening_top10_share=top10_point,
                listening_top10_share_ci_low=top10_ci[0],
                listening_top10_share_ci_high=top10_ci[1],
                scene_churn_jaccard_4w=churn_point,
                scene_churn_jaccard_4w_ci_low=churn_ci[0],
                scene_churn_jaccard_4w_ci_high=churn_ci[1],
                breakout_genres=breakout_genres,
                canonical_genre_count=len(arrays.genres),
                listening_observed_genres=int(np.sum(listening_observed)),
                opportunity_observed_genres=int(np.sum(opportunity_observed)),
                computed_at=computed_at,
            )
        )
    return tuple(rows)


def _top_genres(
    values: FloatArray,
    genres: tuple[str, ...],
    count: int,
) -> set[str]:
    observed = [
        (float(value), genre)
        for value, genre in zip(values, genres, strict=True)
        if math.isfinite(value)
    ]
    observed.sort(reverse=True)
    return {genre for _value, genre in observed[:count]}


def _optional_float(value: np.float64 | float) -> float | None:
    result = float(value)
    return result if math.isfinite(result) else None


def _required_interval(
    samples: FloatArray,
    point: float,
) -> tuple[float, float]:
    lower, upper = percentile_interval(samples, point)
    if lower is None or upper is None:
        raise AssertionError("required interval unexpectedly missing")
    return lower, upper
