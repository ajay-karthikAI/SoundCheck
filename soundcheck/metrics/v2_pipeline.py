"""Coverage-gated hierarchical weekly metrics for taxonomy v2."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

import numpy as np
import numpy.typing as npt

from soundcheck.metrics.statistics import (
    bootstrap_sum,
    cumulative_delta,
    ewma,
    hhi,
    jaccard_similarity,
    percentile_interval,
    shannon_entropy,
    top_k_share,
    within_week_zscores,
)
from soundcheck.metrics.v2_models import (
    ConversationReceiptV2,
    EcosystemWeekV2,
    GenreWeekV2,
    ListeningReceiptV2,
    MacroFamilyWeekV2,
    MetricContext,
    MetricEstimateV2,
    MetricEvidenceV2,
    MetricName,
    MetricsV2Batch,
    SupplyReceiptV2,
)
from soundcheck.metrics.v2_statistics import (
    hierarchical_beta_binomial_shrink,
    hierarchical_gamma_poisson_shrink,
    kish_effective_n,
    within_peer_family_zscores,
)
from soundcheck.taxonomy import GenreTaxonomy

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
CellKey = tuple[date, str]

DEFAULT_V2_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_V2_BOOTSTRAP_SEED = 20_260_726
TREND_HALFLIFE_WEEKS = 3.0
SPIKE_STANDARD_DEVIATIONS = 2.5


@dataclass(slots=True)
class _ConversationCell:
    scores: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    post_uris: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _ListeningCell:
    scores: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    playcount_delta: float = 0.0
    listeners_delta: float = 0.0
    artist_keys: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _SupplyCell:
    weights: list[float] = field(default_factory=list)
    release_group_mbids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _Arrays:
    weeks: tuple[date, ...]
    genre_ids: tuple[str, ...]
    family_ids: tuple[str, ...]
    eligible: BoolArray
    statuses: tuple[tuple[str, ...], ...]
    conversation_raw: FloatArray
    listening_raw: FloatArray
    listening_playcount: FloatArray
    listening_listeners: FloatArray
    supply_raw: FloatArray
    conversation_shrunk: FloatArray
    supply_shrunk: FloatArray
    conversation_effective_n: FloatArray
    listening_effective_n: FloatArray
    supply_effective_n: FloatArray
    conversation_sub_weight: FloatArray
    conversation_family_weight: FloatArray
    conversation_combined_weight: FloatArray
    supply_family_prior: FloatArray
    supply_global_prior: FloatArray
    supply_sub_weight: FloatArray
    supply_family_weight: FloatArray
    supply_combined_weight: FloatArray
    points: dict[MetricContext, dict[MetricName, FloatArray]]
    samples: dict[MetricContext, dict[MetricName, FloatArray]]
    conversation_samples_raw: FloatArray
    listening_samples_raw: FloatArray
    supply_samples_raw: FloatArray
    conversation_samples_shrunk: FloatArray
    supply_samples_shrunk: FloatArray


@dataclass(frozen=True, slots=True)
class _Trend:
    points: dict[MetricContext, dict[MetricName, FloatArray]]
    samples: dict[MetricContext, dict[MetricName, FloatArray]]
    spikes: dict[MetricContext, dict[MetricName, BoolArray]]


@dataclass(frozen=True, slots=True)
class _MacroArrays:
    family_ids: tuple[str, ...]
    eligible: BoolArray
    conversation_raw: FloatArray
    listening_raw: FloatArray
    supply_raw: FloatArray
    conversation_effective_n: FloatArray
    listening_effective_n: FloatArray
    supply_effective_n: FloatArray
    points: dict[MetricName, FloatArray]
    samples: dict[MetricName, FloatArray]
    trend_points: dict[MetricName, FloatArray]
    trend_samples: dict[MetricName, FloatArray]
    spikes: dict[MetricName, BoolArray]


def _optional(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def _aggregate_evidence(
    evidence: MetricEvidenceV2,
) -> tuple[
    dict[CellKey, _ConversationCell],
    dict[CellKey, _ListeningCell],
    dict[CellKey, _SupplyCell],
]:
    conversation: dict[CellKey, _ConversationCell] = defaultdict(_ConversationCell)
    for conversation_item in evidence.conversation:
        conversation_cell = conversation[
            (conversation_item.week_start, conversation_item.genre_id)
        ]
        conversation_cell.scores.append(conversation_item.weighted_score)
        conversation_cell.weights.append(conversation_item.membership_weight)
        conversation_cell.post_uris.add(conversation_item.post_uri)

    listening_units: dict[
        tuple[date, str, str],
        tuple[float, float, float],
    ] = {}
    for listening_item in evidence.listening_candidates:
        previous = (
            None
            if listening_item.previous_playcount is None
            or listening_item.previous_listeners is None
            else (
                listening_item.previous_playcount,
                listening_item.previous_listeners,
            )
        )
        delta = cumulative_delta(
            previous,
            (listening_item.playcount, listening_item.listeners),
        )
        if delta is None:
            continue
        weighted_playcount = listening_item.membership_weight * delta[0]
        weighted_listeners = listening_item.membership_weight * delta[1]
        listening_units[
            (
                listening_item.week_start,
                listening_item.genre_id,
                listening_item.artist_key,
            )
        ] = (
            weighted_playcount,
            weighted_listeners,
            listening_item.membership_weight,
        )
    listening: dict[CellKey, _ListeningCell] = defaultdict(_ListeningCell)
    for (week, genre_id, artist_key), (
        playcount_delta,
        listeners_delta,
        weight,
    ) in listening_units.items():
        listening_cell = listening[(week, genre_id)]
        listening_cell.playcount_delta += playcount_delta
        listening_cell.listeners_delta += listeners_delta
        listening_cell.scores.append(playcount_delta + 5.0 * listeners_delta)
        listening_cell.weights.append(weight)
        listening_cell.artist_keys.add(artist_key)

    supply: dict[CellKey, _SupplyCell] = defaultdict(_SupplyCell)
    seen_releases: set[tuple[date, str, str]] = set()
    for supply_item in evidence.supply:
        identity = (
            supply_item.week_start,
            supply_item.genre_id,
            supply_item.release_group_mbid,
        )
        if identity in seen_releases:
            continue
        seen_releases.add(identity)
        supply_cell = supply[(supply_item.week_start, supply_item.genre_id)]
        supply_cell.weights.append(supply_item.membership_weight)
        supply_cell.release_group_mbids.add(supply_item.release_group_mbid)
    return dict(conversation), dict(listening), dict(supply)


def _metric_dict(shape: tuple[int, ...]) -> dict[MetricName, FloatArray]:
    metric_names: tuple[MetricName, ...] = (
        "conversation",
        "listening",
        "supply",
        "opportunity",
        "discovery_gap",
    )
    return {
        name: np.full(shape, np.nan, dtype=np.float64)
        for name in metric_names
    }


def _context_points(
    conversation: FloatArray,
    listening: FloatArray,
    supply: FloatArray,
    family_ids: tuple[str, ...],
    *,
    peer: bool,
) -> dict[MetricName, FloatArray]:
    week_count, genre_count = conversation.shape
    result = _metric_dict((week_count, genre_count))
    for week_index in range(week_count):
        if peer:
            z_conversation = within_peer_family_zscores(
                [_optional(value) for value in conversation[week_index]],
                family_ids,
            )
            z_listening = within_peer_family_zscores(
                [_optional(value) for value in listening[week_index]],
                family_ids,
            )
            z_supply = within_peer_family_zscores(
                [_optional(value) for value in supply[week_index]],
                family_ids,
            )
        else:
            z_conversation = within_week_zscores(
                [_optional(value) for value in conversation[week_index]]
            )
            z_listening = within_week_zscores(
                [_optional(value) for value in listening[week_index]]
            )
            z_supply = within_week_zscores(
                [_optional(value) for value in supply[week_index]]
            )
        result["conversation"][week_index] = z_conversation
        result["listening"][week_index] = z_listening
        result["supply"][week_index] = z_supply
    result["opportunity"] = (
        (result["conversation"] + result["listening"]) / 2.0
        - result["supply"]
    )
    result["discovery_gap"] = result["listening"] - result["conversation"]
    return result


def _build_arrays(
    evidence: MetricEvidenceV2,
    taxonomy: GenreTaxonomy,
    *,
    bootstrap_resamples: int,
    bootstrap_seed: int,
) -> tuple[
    _Arrays,
    dict[CellKey, _ConversationCell],
    dict[CellKey, _ListeningCell],
    dict[CellKey, _SupplyCell],
]:
    conversation_cells, listening_cells, supply_cells = _aggregate_evidence(evidence)
    weeks = tuple(sorted({row.week_start for row in evidence.coverage}))
    genres = tuple(genre.genre_id for genre in taxonomy.genres)
    families = tuple(genre.macro_family_id for genre in taxonomy.genres)
    coverage_by_key = {
        (row.week_start, row.genre_id): row
        for row in evidence.coverage
    }
    shape = (len(weeks), len(genres))
    sample_shape = (len(weeks), bootstrap_resamples, len(genres))
    eligible = np.zeros(shape, dtype=np.bool_)
    statuses: list[tuple[str, ...]] = []
    conversation_raw = np.full(shape, np.nan, dtype=np.float64)
    listening_raw = np.full(shape, np.nan, dtype=np.float64)
    listening_playcount = np.full(shape, np.nan, dtype=np.float64)
    listening_listeners = np.full(shape, np.nan, dtype=np.float64)
    supply_raw = np.full(shape, np.nan, dtype=np.float64)
    conversation_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    listening_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    supply_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    conversation_effective_n = np.full(shape, np.nan, dtype=np.float64)
    listening_effective_n = np.full(shape, np.nan, dtype=np.float64)
    supply_effective_n = np.full(shape, np.nan, dtype=np.float64)
    generator = np.random.default_rng(bootstrap_seed)

    for week_index, week in enumerate(weeks):
        week_statuses: list[str] = []
        for genre_index, genre_id in enumerate(genres):
            key = (week, genre_id)
            coverage = coverage_by_key[key]
            conversation = conversation_cells.get(key)
            listening = listening_cells.get(key)
            supply = supply_cells.get(key)
            coverage_ready = coverage.eligibility_state == "ready"
            evidence_ready = (
                conversation is not None
                and listening is not None
                and supply is not None
            )
            is_eligible = coverage_ready and evidence_ready
            eligible[week_index, genre_index] = is_eligible
            week_statuses.append(
                "ready"
                if is_eligible
                else "evidence_mismatch"
                if coverage_ready
                else coverage.eligibility_state
            )
            if not is_eligible:
                continue
            assert conversation is not None
            assert listening is not None
            assert supply is not None
            conversation_raw[week_index, genre_index] = sum(conversation.scores)
            listening_raw[week_index, genre_index] = sum(listening.scores)
            listening_playcount[week_index, genre_index] = (
                listening.playcount_delta
            )
            listening_listeners[week_index, genre_index] = (
                listening.listeners_delta
            )
            supply_raw[week_index, genre_index] = sum(supply.weights)
            conversation_effective_n[week_index, genre_index] = kish_effective_n(
                conversation.weights
            )
            listening_effective_n[week_index, genre_index] = kish_effective_n(
                listening.weights
            )
            supply_effective_n[week_index, genre_index] = kish_effective_n(
                supply.weights
            )
            conversation_samples[week_index, :, genre_index] = bootstrap_sum(
                conversation.scores,
                resamples=bootstrap_resamples,
                generator=generator,
            )
            listening_samples[week_index, :, genre_index] = bootstrap_sum(
                listening.scores,
                resamples=bootstrap_resamples,
                generator=generator,
            )
            supply_samples[week_index, :, genre_index] = bootstrap_sum(
                supply.weights,
                resamples=bootstrap_resamples,
                generator=generator,
            )
        statuses.append(tuple(week_statuses))

    conversation_shrunk = np.full(shape, np.nan, dtype=np.float64)
    supply_shrunk = np.full(shape, np.nan, dtype=np.float64)
    conversation_sub_weight = np.full(shape, np.nan, dtype=np.float64)
    conversation_family_weight = np.full(shape, np.nan, dtype=np.float64)
    conversation_combined_weight = np.full(shape, np.nan, dtype=np.float64)
    supply_family_prior = np.full(shape, np.nan, dtype=np.float64)
    supply_global_prior = np.full(shape, np.nan, dtype=np.float64)
    supply_sub_weight = np.full(shape, np.nan, dtype=np.float64)
    supply_family_weight = np.full(shape, np.nan, dtype=np.float64)
    supply_combined_weight = np.full(shape, np.nan, dtype=np.float64)
    conversation_samples_shrunk = np.full_like(conversation_samples, np.nan)
    supply_samples_shrunk = np.full_like(supply_samples, np.nan)

    for week_index in range(len(weeks)):
        indices = np.flatnonzero(eligible[week_index])
        if len(indices) == 0:
            continue
        family_subset = tuple(families[index] for index in indices)
        conversation_fit = hierarchical_beta_binomial_shrink(
            conversation_raw[week_index, indices] * 2.0,
            family_subset,
        )
        supply_fit = hierarchical_gamma_poisson_shrink(
            supply_raw[week_index, indices],
            family_subset,
        )
        conversation_shrunk[week_index, indices] = (
            conversation_fit.posterior_counts / 2.0
        )
        conversation_sub_weight[week_index, indices] = (
            conversation_fit.subgenre_shrinkage_weights
        )
        conversation_family_weight[week_index, indices] = (
            conversation_fit.family_shrinkage_weights
        )
        conversation_combined_weight[week_index, indices] = (
            conversation_fit.combined_shrinkage_weights
        )
        supply_shrunk[week_index, indices] = supply_fit.posterior_rates
        supply_family_prior[week_index, indices] = (
            supply_fit.family_prior_means
        )
        supply_global_prior[week_index, indices] = supply_fit.global_prior_mean
        supply_sub_weight[week_index, indices] = (
            supply_fit.subgenre_shrinkage_weights
        )
        supply_family_weight[week_index, indices] = (
            supply_fit.family_shrinkage_weights
        )
        supply_combined_weight[week_index, indices] = (
            supply_fit.combined_shrinkage_weights
        )
        for sample_index in range(bootstrap_resamples):
            conversation_sample_fit = hierarchical_beta_binomial_shrink(
                conversation_samples[week_index, sample_index, indices] * 2.0,
                family_subset,
            )
            supply_sample_fit = hierarchical_gamma_poisson_shrink(
                supply_samples[week_index, sample_index, indices],
                family_subset,
            )
            conversation_samples_shrunk[
                week_index, sample_index, indices
            ] = conversation_sample_fit.posterior_counts / 2.0
            supply_samples_shrunk[
                week_index, sample_index, indices
            ] = supply_sample_fit.posterior_rates

    transformed_conversation = np.log1p(conversation_shrunk)
    transformed_listening = np.log1p(listening_raw)
    transformed_supply = np.log1p(supply_shrunk)
    points: dict[MetricContext, dict[MetricName, FloatArray]] = {
        "global": _context_points(
            transformed_conversation,
            transformed_listening,
            transformed_supply,
            families,
            peer=False,
        ),
        "peer_family": _context_points(
            transformed_conversation,
            transformed_listening,
            transformed_supply,
            families,
            peer=True,
        ),
    }
    sample_contexts: tuple[MetricContext, ...] = ("global", "peer_family")
    samples: dict[MetricContext, dict[MetricName, FloatArray]] = {
        context: _metric_dict(sample_shape)
        for context in sample_contexts
    }
    for sample_index in (
        range(bootstrap_resamples)
        if bool(np.any(eligible))
        else ()
    ):
        context_modes: tuple[tuple[MetricContext, bool], ...] = (
            ("global", False),
            ("peer_family", True),
        )
        for context, peer in context_modes:
            sample_points = _context_points(
                np.log1p(conversation_samples_shrunk[:, sample_index, :]),
                np.log1p(listening_samples[:, sample_index, :]),
                np.log1p(supply_samples_shrunk[:, sample_index, :]),
                families,
                peer=peer,
            )
            for metric_name, values in sample_points.items():
                samples[context][metric_name][:, sample_index, :] = values

    return (
        _Arrays(
            weeks=weeks,
            genre_ids=genres,
            family_ids=families,
            eligible=eligible,
            statuses=tuple(statuses),
            conversation_raw=conversation_raw,
            listening_raw=listening_raw,
            listening_playcount=listening_playcount,
            listening_listeners=listening_listeners,
            supply_raw=supply_raw,
            conversation_shrunk=conversation_shrunk,
            supply_shrunk=supply_shrunk,
            conversation_effective_n=conversation_effective_n,
            listening_effective_n=listening_effective_n,
            supply_effective_n=supply_effective_n,
            conversation_sub_weight=conversation_sub_weight,
            conversation_family_weight=conversation_family_weight,
            conversation_combined_weight=conversation_combined_weight,
            supply_family_prior=supply_family_prior,
            supply_global_prior=supply_global_prior,
            supply_sub_weight=supply_sub_weight,
            supply_family_weight=supply_family_weight,
            supply_combined_weight=supply_combined_weight,
            points=points,
            samples=samples,
            conversation_samples_raw=conversation_samples,
            listening_samples_raw=listening_samples,
            supply_samples_raw=supply_samples,
            conversation_samples_shrunk=conversation_samples_shrunk,
            supply_samples_shrunk=supply_samples_shrunk,
        ),
        conversation_cells,
        listening_cells,
        supply_cells,
    )


def _trends(
    points: dict[MetricContext, dict[MetricName, FloatArray]],
    samples: dict[MetricContext, dict[MetricName, FloatArray]],
    family_ids: tuple[str, ...],
) -> _Trend:
    trend_points = {
        context: _metric_dict(next(iter(metrics.values())).shape)
        for context, metrics in points.items()
    }
    trend_samples = {
        context: _metric_dict(next(iter(metrics.values())).shape)
        for context, metrics in samples.items()
    }
    spikes = {
        context: {
            name: np.zeros(values.shape, dtype=np.bool_)
            for name, values in metrics.items()
        }
        for context, metrics in points.items()
    }
    contexts: tuple[MetricContext, ...] = tuple(points)
    axis_names: tuple[MetricName, ...] = (
        "conversation",
        "listening",
        "supply",
    )
    for context in contexts:
        for metric_name in axis_names:
            values = points[context][metric_name]
            sample_values = samples[context][metric_name]
            for entity_index in range(values.shape[1]):
                if not bool(np.any(np.isfinite(values[:, entity_index]))):
                    continue
                trend_points[context][metric_name][:, entity_index] = ewma(
                    [_optional(value) for value in values[:, entity_index]],
                    halflife=TREND_HALFLIFE_WEEKS,
                )
                for sample_index in range(sample_values.shape[1]):
                    trend_samples[context][metric_name][
                        :, sample_index, entity_index
                    ] = ewma(
                        [
                            _optional(value)
                            for value in sample_values[
                                :, sample_index, entity_index
                            ]
                        ],
                        halflife=TREND_HALFLIFE_WEEKS,
                    )
            residuals = values - trend_points[context][metric_name]
            for week_index in range(values.shape[0]):
                if context == "global":
                    groups: tuple[tuple[int, ...], ...] = (
                        tuple(range(values.shape[1])),
                    )
                else:
                    groups = tuple(
                        tuple(
                            index
                            for index, family_id in enumerate(family_ids)
                            if family_id == family
                        )
                        for family in sorted(set(family_ids))
                    )
                for group in groups:
                    observed = np.asarray(
                        [
                            residuals[week_index, index]
                            for index in group
                            if math.isfinite(residuals[week_index, index])
                        ]
                    )
                    standard_deviation = (
                        float(np.std(observed, ddof=0))
                        if len(observed)
                        else 0.0
                    )
                    if standard_deviation <= 0.0:
                        continue
                    for index in group:
                        residual = residuals[week_index, index]
                        spikes[context][metric_name][week_index, index] = bool(
                            math.isfinite(residual)
                            and residual
                            > SPIKE_STANDARD_DEVIATIONS * standard_deviation
                        )
    return _Trend(
        points=trend_points,
        samples=trend_samples,
        spikes=spikes,
    )


def _breakouts(
    conversation: FloatArray,
    listening: FloatArray,
    family_ids: tuple[str, ...],
    *,
    peer: bool,
) -> BoolArray:
    result = np.zeros(conversation.shape, dtype=np.bool_)
    for week_index in range(conversation.shape[0]):
        groups = (
            tuple(
                tuple(
                    index
                    for index, family_id in enumerate(family_ids)
                    if family_id == family
                )
                for family in sorted(set(family_ids))
            )
            if peer
            else (tuple(range(conversation.shape[1])),)
        )
        for group in groups:
            observed = [
                index
                for index in group
                if math.isfinite(conversation[week_index, index])
                and math.isfinite(listening[week_index, index])
            ]
            if not observed:
                continue
            listening_threshold = float(
                np.quantile(listening[week_index, observed], 0.9)
            )
            conversation_median = float(
                np.median(conversation[week_index, observed])
            )
            for index in observed:
                result[week_index, index] = bool(
                    listening[week_index, index] >= listening_threshold
                    and conversation[week_index, index] < conversation_median
                )
    return result


def _macro_arrays(arrays: _Arrays) -> _MacroArrays:
    families = tuple(sorted(set(arrays.family_ids)))
    shape = (len(arrays.weeks), len(families))
    sample_shape = (
        len(arrays.weeks),
        arrays.conversation_samples_raw.shape[1],
        len(families),
    )
    eligible = np.zeros(shape, dtype=np.bool_)
    raw_conversation = np.full(shape, np.nan, dtype=np.float64)
    raw_listening = np.full(shape, np.nan, dtype=np.float64)
    raw_supply = np.full(shape, np.nan, dtype=np.float64)
    effective_conversation = np.full(shape, np.nan, dtype=np.float64)
    effective_listening = np.full(shape, np.nan, dtype=np.float64)
    effective_supply = np.full(shape, np.nan, dtype=np.float64)
    transformed_conversation = np.full(shape, np.nan, dtype=np.float64)
    transformed_listening = np.full(shape, np.nan, dtype=np.float64)
    transformed_supply = np.full(shape, np.nan, dtype=np.float64)
    conversation_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    listening_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    supply_samples = np.full(sample_shape, np.nan, dtype=np.float64)
    for family_index, family in enumerate(families):
        genre_indices = np.asarray(
            [
                index
                for index, family_id in enumerate(arrays.family_ids)
                if family_id == family
            ],
            dtype=np.int64,
        )
        for week_index in range(len(arrays.weeks)):
            active = genre_indices[arrays.eligible[week_index, genre_indices]]
            if len(active) == 0:
                continue
            eligible[week_index, family_index] = True
            raw_conversation[week_index, family_index] = float(
                np.sum(arrays.conversation_raw[week_index, active])
            )
            raw_listening[week_index, family_index] = float(
                np.sum(arrays.listening_raw[week_index, active])
            )
            raw_supply[week_index, family_index] = float(
                np.sum(arrays.supply_raw[week_index, active])
            )
            effective_conversation[week_index, family_index] = float(
                np.sum(arrays.conversation_effective_n[week_index, active])
            )
            effective_listening[week_index, family_index] = float(
                np.sum(arrays.listening_effective_n[week_index, active])
            )
            effective_supply[week_index, family_index] = float(
                np.sum(arrays.supply_effective_n[week_index, active])
            )
            transformed_conversation[week_index, family_index] = math.log1p(
                float(np.sum(arrays.conversation_shrunk[week_index, active]))
            )
            transformed_listening[week_index, family_index] = math.log1p(
                raw_listening[week_index, family_index]
            )
            transformed_supply[week_index, family_index] = math.log1p(
                float(np.sum(arrays.supply_shrunk[week_index, active]))
            )
            conversation_samples[week_index, :, family_index] = np.sum(
                arrays.conversation_samples_shrunk[week_index, :, active],
                axis=0,
            )
            listening_samples[week_index, :, family_index] = np.sum(
                arrays.listening_samples_raw[week_index, :, active],
                axis=0,
            )
            supply_samples[week_index, :, family_index] = np.sum(
                arrays.supply_samples_shrunk[week_index, :, active],
                axis=0,
            )
    points = _context_points(
        transformed_conversation,
        transformed_listening,
        transformed_supply,
        families,
        peer=False,
    )
    samples = _metric_dict(sample_shape)
    for sample_index in (
        range(sample_shape[1])
        if bool(np.any(eligible))
        else ()
    ):
        sample_points = _context_points(
            np.log1p(conversation_samples[:, sample_index, :]),
            np.log1p(listening_samples[:, sample_index, :]),
            np.log1p(supply_samples[:, sample_index, :]),
            families,
            peer=False,
        )
        for metric_name, values in sample_points.items():
            samples[metric_name][:, sample_index, :] = values
    generic_trends = _trends(
        {"global": points},
        {"global": samples},
        families,
    )
    return _MacroArrays(
        family_ids=families,
        eligible=eligible,
        conversation_raw=raw_conversation,
        listening_raw=raw_listening,
        supply_raw=raw_supply,
        conversation_effective_n=effective_conversation,
        listening_effective_n=effective_listening,
        supply_effective_n=effective_supply,
        points=points,
        samples=samples,
        trend_points=generic_trends.points["global"],
        trend_samples=generic_trends.samples["global"],
        spikes=generic_trends.spikes["global"],
    )


def _estimate_rows(
    arrays: _Arrays,
    trends: _Trend,
    macro: _MacroArrays,
    taxonomy_version: str,
    computed_at: datetime,
) -> tuple[MetricEstimateV2, ...]:
    rows: list[MetricEstimateV2] = []
    axis_names: tuple[MetricName, ...] = (
        "conversation",
        "listening",
        "supply",
    )
    for week_index, week in enumerate(arrays.weeks):
        for genre_index, genre_id in enumerate(arrays.genre_ids):
            status = arrays.statuses[week_index][genre_index]
            for context in ("global", "peer_family"):
                for metric_name in (
                    "conversation",
                    "listening",
                    "supply",
                    "opportunity",
                    "discovery_gap",
                ):
                    point = _optional(
                        arrays.points[context][metric_name][week_index, genre_index]
                    )
                    interval = percentile_interval(
                        arrays.samples[context][metric_name][
                            week_index, :, genre_index
                        ],
                        point,
                    )
                    if metric_name in axis_names:
                        trend_point = _optional(
                            trends.points[context][metric_name][
                                week_index, genre_index
                            ]
                        )
                        trend_interval = percentile_interval(
                            trends.samples[context][metric_name][
                                week_index, :, genre_index
                            ],
                            trend_point,
                        )
                        spike = (
                            bool(
                                trends.spikes[context][metric_name][
                                    week_index, genre_index
                                ]
                            )
                            if point is not None
                            else None
                        )
                    else:
                        trend_point = None
                        trend_interval = (None, None)
                        spike = None
                    rows.append(
                        MetricEstimateV2.model_validate(
                            {
                                "taxonomy_version": taxonomy_version,
                                "week_start": week,
                                "scope_type": "genre",
                                "scope_id": genre_id,
                                "macro_family_id": arrays.family_ids[genre_index],
                                "context": context,
                                "metric_name": metric_name,
                                "estimate_status": status,
                                "estimate": point,
                                "ci_low": interval[0],
                                "ci_high": interval[1],
                                "ewma": trend_point,
                                "ewma_ci_low": trend_interval[0],
                                "ewma_ci_high": trend_interval[1],
                                "spike": spike,
                                "computed_at": computed_at,
                            }
                        )
                    )
        for family_index, family_id in enumerate(macro.family_ids):
            status = (
                "ready"
                if macro.eligible[week_index, family_index]
                else "insufficient_listening"
            )
            metric_names: tuple[MetricName, ...] = (
                "conversation",
                "listening",
                "supply",
                "opportunity",
                "discovery_gap",
            )
            for metric_name in metric_names:
                point = _optional(
                    macro.points[metric_name][week_index, family_index]
                )
                interval = percentile_interval(
                    macro.samples[metric_name][week_index, :, family_index],
                    point,
                )
                if metric_name in axis_names:
                    trend_point = _optional(
                        macro.trend_points[metric_name][
                            week_index, family_index
                        ]
                    )
                    trend_interval = percentile_interval(
                        macro.trend_samples[metric_name][
                            week_index, :, family_index
                        ],
                        trend_point,
                    )
                    spike = (
                        bool(
                            macro.spikes[metric_name][
                                week_index, family_index
                            ]
                        )
                        if point is not None
                        else None
                    )
                else:
                    trend_point = None
                    trend_interval = (None, None)
                    spike = None
                rows.append(
                    MetricEstimateV2.model_validate(
                        {
                            "taxonomy_version": taxonomy_version,
                            "week_start": week,
                            "scope_type": "macro_family",
                            "scope_id": family_id,
                            "macro_family_id": family_id,
                            "context": "global",
                            "metric_name": metric_name,
                            "estimate_status": status,
                            "estimate": point,
                            "ci_low": interval[0],
                            "ci_high": interval[1],
                            "ewma": trend_point,
                            "ewma_ci_low": trend_interval[0],
                            "ewma_ci_high": trend_interval[1],
                            "spike": spike,
                            "computed_at": computed_at,
                        }
                    )
                )
    return tuple(rows)


def _ecosystem_measure(
    listening: FloatArray,
    conversation: FloatArray,
    listening_samples: FloatArray,
    conversation_samples: FloatArray,
    indices: list[int],
    *,
    top_k: int,
) -> tuple[
    float | None,
    tuple[float | None, float | None],
    float | None,
    tuple[float | None, float | None],
    float | None,
    tuple[float | None, float | None],
    float | None,
    tuple[float | None, float | None],
]:
    if not indices:
        return None, (None, None), None, (None, None), None, (None, None), None, (
            None,
            None,
        )
    listening_values = listening[indices]
    conversation_values = conversation[indices]
    if float(np.sum(listening_values)) <= 0.0:
        return None, (None, None), None, (None, None), None, (None, None), None, (
            None,
            None,
        )
    entropy_point = shannon_entropy(listening_values.tolist())
    effective_point = math.exp(entropy_point)
    top_point = top_k_share(listening_values.tolist(), k=top_k)
    hhi_point = (
        hhi(conversation_values.tolist())
        if float(np.sum(conversation_values)) > 0.0
        else None
    )
    entropy_samples = np.full(listening_samples.shape[0], np.nan)
    effective_samples = np.full_like(entropy_samples, np.nan)
    top_samples = np.full_like(entropy_samples, np.nan)
    hhi_samples = np.full_like(entropy_samples, np.nan)
    for sample_index in range(listening_samples.shape[0]):
        listening_sample = listening_samples[sample_index, indices]
        conversation_sample = conversation_samples[sample_index, indices]
        if float(np.sum(listening_sample)) > 0.0:
            entropy_samples[sample_index] = shannon_entropy(
                listening_sample.tolist()
            )
            effective_samples[sample_index] = math.exp(
                entropy_samples[sample_index]
            )
            top_samples[sample_index] = top_k_share(
                listening_sample.tolist(),
                k=top_k,
            )
        if float(np.sum(conversation_sample)) > 0.0:
            hhi_samples[sample_index] = hhi(conversation_sample.tolist())
    return (
        entropy_point,
        percentile_interval(entropy_samples, entropy_point),
        effective_point,
        percentile_interval(effective_samples, effective_point),
        hhi_point,
        percentile_interval(hhi_samples, hhi_point),
        top_point,
        percentile_interval(top_samples, top_point),
    )


def _ecosystem_rows(
    arrays: _Arrays,
    breakouts_global: BoolArray,
    taxonomy_version: str,
    computed_at: datetime,
) -> tuple[EcosystemWeekV2, ...]:
    rows: list[EcosystemWeekV2] = []
    week_index_by_date = {week: index for index, week in enumerate(arrays.weeks)}
    families = tuple(sorted(set(arrays.family_ids)))
    for week_index, week in enumerate(arrays.weeks):
        scopes: tuple[
            tuple[
                Literal["global", "macro_family"],
                str,
                list[int],
                int,
            ],
            ...,
        ] = (
            ("global", "global", list(np.flatnonzero(arrays.eligible[week_index])), 10),
            *(
                (
                    "macro_family",
                    family,
                    [
                        index
                        for index, family_id in enumerate(arrays.family_ids)
                        if family_id == family
                        and arrays.eligible[week_index, index]
                    ],
                    3,
                )
                for family in families
            ),
        )
        for scope_type, scope_id, indices, top_k in scopes:
            (
                entropy_point,
                entropy_interval,
                effective_point,
                effective_interval,
                hhi_point,
                hhi_interval,
                top_point,
                top_interval,
            ) = _ecosystem_measure(
                arrays.listening_raw[week_index],
                arrays.conversation_raw[week_index],
                arrays.listening_samples_raw[week_index],
                arrays.conversation_samples_raw[week_index],
                indices,
                top_k=top_k,
            )
            prior_week = week.fromordinal(week.toordinal() - 28)
            prior_index = week_index_by_date.get(prior_week)
            churn_interval: tuple[float | None, float | None]
            if prior_index is None:
                churn_point = None
                churn_interval = (None, None)
            else:
                prior_indices = [
                    index
                    for index in indices
                    if arrays.eligible[prior_index, index]
                ]
                current_ranked = sorted(
                    indices,
                    key=lambda index: arrays.points["global"]["opportunity"][
                        week_index, index
                    ],
                    reverse=True,
                )[:25]
                prior_ranked = sorted(
                    prior_indices,
                    key=lambda index: arrays.points["global"]["opportunity"][
                        prior_index, index
                    ],
                    reverse=True,
                )[:25]
                churn_point = jaccard_similarity(
                    {arrays.genre_ids[index] for index in current_ranked},
                    {arrays.genre_ids[index] for index in prior_ranked},
                )
                churn_samples = np.full(
                    arrays.conversation_samples_raw.shape[1],
                    np.nan,
                )
                for sample_index in range(len(churn_samples)):
                    current_sample = sorted(
                        indices,
                        key=lambda index: arrays.samples["global"][
                            "opportunity"
                        ][week_index, sample_index, index],
                        reverse=True,
                    )[:25]
                    prior_sample = sorted(
                        prior_indices,
                        key=lambda index: arrays.samples["global"][
                            "opportunity"
                        ][prior_index, sample_index, index],
                        reverse=True,
                    )[:25]
                    churn_samples[sample_index] = jaccard_similarity(
                        {arrays.genre_ids[index] for index in current_sample},
                        {arrays.genre_ids[index] for index in prior_sample},
                    )
                churn_interval = percentile_interval(
                    churn_samples,
                    churn_point,
                )
            status: Literal["ready", "insufficient_evidence"] = (
                "ready"
                if entropy_point is not None and hhi_point is not None
                else "insufficient_evidence"
            )
            iso = week.isocalendar()
            rows.append(
                EcosystemWeekV2(
                    taxonomy_version=taxonomy_version,
                    week_start=week,
                    iso_year=iso.year,
                    iso_week=iso.week,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    estimate_status=status,
                    listening_entropy=entropy_point,
                    listening_entropy_ci_low=entropy_interval[0],
                    listening_entropy_ci_high=entropy_interval[1],
                    effective_genres=effective_point,
                    effective_genres_ci_low=effective_interval[0],
                    effective_genres_ci_high=effective_interval[1],
                    conversation_hhi=hhi_point,
                    conversation_hhi_ci_low=hhi_interval[0],
                    conversation_hhi_ci_high=hhi_interval[1],
                    listening_top_share=top_point,
                    listening_top_share_ci_low=top_interval[0],
                    listening_top_share_ci_high=top_interval[1],
                    listening_top_share_k=top_k,
                    churn_jaccard_4w=churn_point,
                    churn_jaccard_4w_ci_low=churn_interval[0],
                    churn_jaccard_4w_ci_high=churn_interval[1],
                    breakout_genres=tuple(
                        arrays.genre_ids[index]
                        for index in indices
                        if breakouts_global[week_index, index]
                    ),
                    eligible_genres=len(indices),
                    computed_at=computed_at,
                )
            )
    return tuple(rows)


def build_metrics_v2(
    evidence: MetricEvidenceV2,
    taxonomy: GenreTaxonomy,
    *,
    computed_at: datetime | None = None,
    bootstrap_resamples: int = DEFAULT_V2_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_V2_BOOTSTRAP_SEED,
) -> MetricsV2Batch:
    """Build only the requested taxonomy version's parallel metric artifacts."""
    if evidence.taxonomy_version != taxonomy.taxonomy_version:
        raise ValueError("evidence and taxonomy versions must match")
    if bootstrap_resamples <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    metric_time = computed_at or datetime.now(UTC)
    if metric_time.tzinfo is None:
        raise ValueError("computed_at must include a timezone")
    metric_time = metric_time.astimezone(UTC)
    if not evidence.coverage:
        return MetricsV2Batch(
            taxonomy_version=taxonomy.taxonomy_version,
            genre_weeks=(),
            macro_family_weeks=(),
            estimates=(),
            ecosystem_weeks=(),
        )
    arrays, conversation_cells, listening_cells, supply_cells = _build_arrays(
        evidence,
        taxonomy,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    trends = _trends(arrays.points, arrays.samples, arrays.family_ids)
    breakout_global = _breakouts(
        arrays.points["global"]["conversation"],
        arrays.points["global"]["listening"],
        arrays.family_ids,
        peer=False,
    )
    breakout_peer = _breakouts(
        arrays.points["peer_family"]["conversation"],
        arrays.points["peer_family"]["listening"],
        arrays.family_ids,
        peer=True,
    )
    coverage_by_key = {
        (row.week_start, row.genre_id): row
        for row in evidence.coverage
    }
    genre_by_id = taxonomy.genre_by_id
    genre_rows: list[GenreWeekV2] = []
    for week_index, week in enumerate(arrays.weeks):
        iso = week.isocalendar()
        for genre_index, genre_id in enumerate(arrays.genre_ids):
            genre = genre_by_id[genre_id]
            key = (week, genre_id)
            conversation = conversation_cells.get(key)
            listening = listening_cells.get(key)
            supply = supply_cells.get(key)
            eligible = bool(arrays.eligible[week_index, genre_index])
            genre_rows.append(
                GenreWeekV2.model_validate(
                    {
                        "taxonomy_version": taxonomy.taxonomy_version,
                        "week_start": week,
                        "iso_year": iso.year,
                        "iso_week": iso.week,
                        "genre_id": genre_id,
                        "display_name": genre.display_name,
                        "macro_family_id": genre.macro_family_id,
                        "parent_genre_id": genre.parent_genre_id,
                        "coverage_state": coverage_by_key[
                            key
                        ].eligibility_state,
                        "estimate_status": arrays.statuses[
                            week_index
                        ][genre_index],
                        "estimate_eligible": eligible,
                        "conversation_score_raw": _optional(
                            arrays.conversation_raw[
                                week_index, genre_index
                            ]
                        ),
                        "listening_playcount_delta": _optional(
                            arrays.listening_playcount[
                                week_index, genre_index
                            ]
                        ),
                        "listening_listeners_delta": _optional(
                            arrays.listening_listeners[
                                week_index, genre_index
                            ]
                        ),
                        "listening_score_raw": _optional(
                            arrays.listening_raw[week_index, genre_index]
                        ),
                        "supply_release_groups_raw": _optional(
                            arrays.supply_raw[week_index, genre_index]
                        ),
                        "conversation_score_shrunk": _optional(
                            arrays.conversation_shrunk[
                                week_index, genre_index
                            ]
                        ),
                        "conversation_effective_n": _optional(
                            arrays.conversation_effective_n[
                                week_index, genre_index
                            ]
                        ),
                        "conversation_subgenre_shrinkage_weight": _optional(
                            arrays.conversation_sub_weight[
                                week_index, genre_index
                            ]
                        ),
                        "conversation_family_shrinkage_weight": _optional(
                            arrays.conversation_family_weight[
                                week_index, genre_index
                            ]
                        ),
                        "conversation_combined_shrinkage_weight": _optional(
                            arrays.conversation_combined_weight[
                                week_index, genre_index
                            ]
                        ),
                        "listening_effective_n": _optional(
                            arrays.listening_effective_n[
                                week_index, genre_index
                            ]
                        ),
                        "listening_shrinkage_weight": 0.0 if eligible else None,
                        "supply_rate_shrunk": _optional(
                            arrays.supply_shrunk[week_index, genre_index]
                        ),
                        "supply_family_prior_mean": _optional(
                            arrays.supply_family_prior[
                                week_index, genre_index
                            ]
                        ),
                        "supply_global_prior_mean": _optional(
                            arrays.supply_global_prior[
                                week_index, genre_index
                            ]
                        ),
                        "supply_effective_n": _optional(
                            arrays.supply_effective_n[
                                week_index, genre_index
                            ]
                        ),
                        "supply_subgenre_shrinkage_weight": _optional(
                            arrays.supply_sub_weight[
                                week_index, genre_index
                            ]
                        ),
                        "supply_family_shrinkage_weight": _optional(
                            arrays.supply_family_weight[
                                week_index, genre_index
                            ]
                        ),
                        "supply_combined_shrinkage_weight": _optional(
                            arrays.supply_combined_weight[
                                week_index, genre_index
                            ]
                        ),
                        "breakout_global": (
                            bool(
                                breakout_global[
                                    week_index, genre_index
                                ]
                            )
                            if eligible
                            else None
                        ),
                        "breakout_peer_family": (
                            bool(
                                breakout_peer[
                                    week_index, genre_index
                                ]
                            )
                            if eligible
                            else None
                        ),
                        "conversation_post_uris": tuple(
                            sorted(
                                conversation.post_uris
                                if conversation
                                else ()
                            )
                        ),
                        "listening_artist_keys": tuple(
                            sorted(
                                listening.artist_keys
                                if listening
                                else ()
                            )
                        ),
                        "supply_release_group_mbids": tuple(
                            sorted(
                                supply.release_group_mbids
                                if supply
                                else ()
                            )
                        ),
                        "computed_at": metric_time,
                    }
                )
            )
    macro = _macro_arrays(arrays)
    family_by_id = {
        family.macro_family_id: family
        for family in taxonomy.macro_families
    }
    macro_rows: list[MacroFamilyWeekV2] = []
    for week_index, week in enumerate(arrays.weeks):
        iso = week.isocalendar()
        for family_index, family_id in enumerate(macro.family_ids):
            member_indices = [
                index
                for index, value in enumerate(arrays.family_ids)
                if value == family_id
            ]
            eligible_indices = [
                index
                for index in member_indices
                if arrays.eligible[week_index, index]
            ]
            state_counts = Counter(
                coverage_by_key[
                    (week, arrays.genre_ids[index])
                ].eligibility_state
                for index in member_indices
            )
            macro_rows.append(
                MacroFamilyWeekV2(
                    taxonomy_version=taxonomy.taxonomy_version,
                    week_start=week,
                    iso_year=iso.year,
                    iso_week=iso.week,
                    macro_family_id=family_id,
                    display_name=family_by_id[family_id].display_name,
                    total_genres=len(member_indices),
                    eligible_genres=len(eligible_indices),
                    estimate_status=(
                        "ready"
                        if eligible_indices
                        else "insufficient_evidence"
                    ),
                    coverage_state_counts_json=json.dumps(
                        dict(sorted(state_counts.items())),
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    conversation_score_raw=_optional(
                        macro.conversation_raw[
                            week_index, family_index
                        ]
                    ),
                    listening_score_raw=_optional(
                        macro.listening_raw[week_index, family_index]
                    ),
                    supply_release_groups_raw=_optional(
                        macro.supply_raw[week_index, family_index]
                    ),
                    conversation_effective_n=_optional(
                        macro.conversation_effective_n[
                            week_index, family_index
                        ]
                    ),
                    listening_effective_n=_optional(
                        macro.listening_effective_n[
                            week_index, family_index
                        ]
                    ),
                    supply_effective_n=_optional(
                        macro.supply_effective_n[
                            week_index, family_index
                        ]
                    ),
                    breakout_genres_global=tuple(
                        arrays.genre_ids[index]
                        for index in eligible_indices
                        if breakout_global[week_index, index]
                    ),
                    breakout_genres_peer=tuple(
                        arrays.genre_ids[index]
                        for index in eligible_indices
                        if breakout_peer[week_index, index]
                    ),
                    computed_at=metric_time,
                )
            )
    estimates = _estimate_rows(
        arrays,
        trends,
        macro,
        taxonomy.taxonomy_version,
        metric_time,
    )
    ecosystem = _ecosystem_rows(
        arrays,
        breakout_global,
        taxonomy.taxonomy_version,
        metric_time,
    )
    conversation_receipts = tuple(
        ConversationReceiptV2(
            taxonomy_version=taxonomy.taxonomy_version,
            week_start=row.week_start,
            genre_id=row.genre_id,
            macro_family_id=row.macro_family_id,
            post_uri=row.post_uri,
            did=row.did,
            created_at=row.created_at,
            text=row.text,
            likes=row.likes,
            reposts=row.reposts,
            replies=row.replies,
            artist_name_raw=row.artist_name_raw,
            resolution_method=row.resolution_method,
            resolution_score=row.resolution_score,
            join_key_type=row.join_key_type,
            membership_weight=row.membership_weight,
            membership_method=row.membership_method,
            membership_confidence=row.membership_confidence,
        )
        for row in evidence.conversation
        if row.did is not None
        and row.created_at is not None
        and row.text is not None
        and row.artist_name_raw is not None
        and row.resolution_method is not None
        and row.resolution_score is not None
        and row.join_key_type is not None
        and row.membership_method is not None
        and row.membership_confidence is not None
    )
    listening_receipts = tuple(
        ListeningReceiptV2(
            taxonomy_version=taxonomy.taxonomy_version,
            week_start=row.week_start,
            genre_id=row.genre_id,
            macro_family_id=row.macro_family_id,
            artist_key=row.artist_key,
            artist_name=row.artist_name,
            artist_mbid=row.artist_mbid,
            playcount=row.playcount,
            listeners=row.listeners,
            previous_playcount=row.previous_playcount,
            previous_listeners=row.previous_listeners,
            playcount_delta=row.playcount - row.previous_playcount,
            listeners_delta=row.listeners - row.previous_listeners,
            fetched_at=row.fetched_at,
            previous_fetched_at=row.previous_fetched_at,
            membership_weight=row.membership_weight,
            membership_method=row.membership_method,
            membership_confidence=row.membership_confidence,
        )
        for row in evidence.listening_candidates
        if row.artist_name is not None
        and row.previous_playcount is not None
        and row.previous_listeners is not None
        and row.fetched_at is not None
        and row.previous_fetched_at is not None
        and row.membership_method is not None
        and row.membership_confidence is not None
        and row.playcount >= row.previous_playcount
        and row.listeners >= row.previous_listeners
    )
    supply_receipts = tuple(
        SupplyReceiptV2(
            taxonomy_version=taxonomy.taxonomy_version,
            week_start=row.week_start,
            genre_id=row.genre_id,
            macro_family_id=row.macro_family_id,
            release_group_mbid=row.release_group_mbid,
            title=row.title,
            artist_credits=row.artist_credits,
            first_release_date=row.first_release_date,
            types=row.types,
            genres=row.genres,
            fetched_at=row.fetched_at,
            membership_weight=row.membership_weight,
        )
        for row in evidence.supply
        if row.title is not None
        and row.first_release_date is not None
        and row.fetched_at is not None
    )
    return MetricsV2Batch(
        taxonomy_version=taxonomy.taxonomy_version,
        genre_weeks=tuple(genre_rows),
        macro_family_weeks=tuple(macro_rows),
        estimates=estimates,
        ecosystem_weeks=ecosystem,
        conversation_evidence=conversation_receipts,
        listening_evidence=listening_receipts,
        supply_evidence=supply_receipts,
    )
