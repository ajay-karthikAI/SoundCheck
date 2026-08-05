"""Build an isolated, deterministic synthetic artifact for UI evaluation.

This module never reads, mutates, or replaces ``data/soundcheck.duckdb``. It
creates a separate DuckDB file whose pipeline manifest is marked
``synthetic_demo``. The data exercises every public API surface while preserving
the production schemas, cumulative Last.fm snapshot rule, ISO-week windows,
uncertainty bands, evidence receipts, and forecast skill labels.

Synthetic output is for local product evaluation only. It must never be
published or described as observed trend evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from soundcheck.briefs.models import GeneratedBrief
from soundcheck.briefs.storage import DuckDBBriefStore
from soundcheck.forecast.models import (
    BacktestRecord,
    ForecastBatch,
    ForecastPrediction,
    ModelScore,
    NextUpPrediction,
)
from soundcheck.forecast.storage import DuckDBForecastStore
from soundcheck.metrics.models import GenreWeekMetric, MetricsBatch, SceneMapPoint
from soundcheck.metrics.pipeline import build_metrics
from soundcheck.metrics.storage import DuckDBMetricStore
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import GenreDefinition, GenreTaxonomy, load_taxonomy

DEFAULT_OUTPUT_PATH = Path("data/soundcheck-demo.duckdb")
PRODUCTION_DATABASE_PATH = Path("data/soundcheck.duckdb")
DEFAULT_WEEKS = 26
DEFAULT_BOOTSTRAP_RESAMPLES = 2_000
DEMO_SEED = 20_260_724
BREAKOUT_INDICES = frozenset({5, 17, 29})
ARTIST_SUFFIXES = ("Collective", "Signal", "Archive")
POST_TEMPLATES = (
    "Synthetic demo receipt: listening to {artist}; the textures keep opening up.",
    "Synthetic demo receipt: {artist} is on repeat in the studio this week.",
    "Synthetic demo receipt: the new {artist} single found a quiet audience.",
)
RELEASE_WORDS = ("Afterimage", "Low Current", "Open Circuit", "Night Index")

type SqlRow = tuple[object, ...]
type TargetAxis = Literal["conversation", "listening"]
type ForecastModel = Literal["naive", "seasonal_naive", "ets", "lightgbm"]


def _append_first_unique(
    destination: list[GenreDefinition],
    candidates: tuple[GenreDefinition, ...],
) -> None:
    for candidate in candidates:
        if candidate not in destination:
            destination.append(candidate)
            return


def _select_demo_genres(
    taxonomy: GenreTaxonomy,
    *,
    per_macro_family: int = 3,
) -> tuple[GenreDefinition, ...]:
    """Select a balanced, deterministic taxonomy sample for synthetic UI data."""
    if per_macro_family <= 0:
        msg = "per_macro_family must be positive"
        raise ValueError(msg)
    selected: list[GenreDefinition] = []
    special_ids = {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
    for family in taxonomy.macro_families:
        if family.macro_family_id == "macro_unclassified":
            continue
        definitions = tuple(
            genre
            for genre in taxonomy.genres
            if genre.macro_family_id == family.macro_family_id
            and genre.genre_id not in special_ids
            and genre.status != "rejected"
        )
        if not definitions:
            continue
        family_selection: list[GenreDefinition] = []
        _append_first_unique(
            family_selection,
            tuple(
                genre
                for genre in definitions
                if genre.genre_id == taxonomy.default_genre_id
            ),
        )
        _append_first_unique(
            family_selection,
            tuple(
                genre
                for genre in definitions
                if genre.status == "enabled"
                and genre.parent_genre_id is not None
            ),
        )
        _append_first_unique(
            family_selection,
            tuple(
                genre
                for genre in definitions
                if genre.status == "candidate"
                and genre.parent_genre_id is not None
            ),
        )
        _append_first_unique(
            family_selection,
            tuple(
                genre
                for genre in definitions
                if genre.parent_genre_id is None
            ),
        )
        for genre in definitions:
            if len(family_selection) >= per_macro_family:
                break
            if genre not in family_selection:
                family_selection.append(genre)
        if len(family_selection) < per_macro_family:
            msg = (
                f"macro family {family.macro_family_id} lacks "
                f"{per_macro_family} demo-safe genres"
            )
            raise ValueError(msg)
        selected.extend(family_selection[:per_macro_family])
    return tuple(selected)


DEMO_TAXONOMY = load_taxonomy()
DEMO_GENRE_DEFINITIONS = _select_demo_genres(DEMO_TAXONOMY)
DEMO_GENRES = tuple(genre.canonical_name for genre in DEMO_GENRE_DEFINITIONS)
DEMO_MACRO_FAMILIES = len(
    {genre.macro_family_id for genre in DEMO_GENRE_DEFINITIONS}
)


class DemoSettings(BaseModel):
    """Validated demo generation inputs."""

    model_config = ConfigDict(frozen=True)

    output_path: Path = DEFAULT_OUTPUT_PATH
    as_of_date: date = Field(default_factory=lambda: datetime.now(UTC).date())
    weeks: int = Field(default=DEFAULT_WEEKS, ge=10, le=52)
    bootstrap_resamples: int = Field(
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
        ge=25,
        le=10_000,
    )

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, output_path: Path) -> Path:
        if output_path.suffix != ".duckdb":
            msg = "demo output must use a .duckdb filename"
            raise ValueError(msg)
        return output_path

    @model_validator(mode="after")
    def protect_production_database(self) -> DemoSettings:
        if self.output_path.resolve() == PRODUCTION_DATABASE_PATH.resolve():
            msg = "the demo generator refuses to overwrite data/soundcheck.duckdb"
            raise ValueError(msg)
        return self


class DemoSummary(BaseModel):
    """Machine-readable generation result."""

    model_config = ConfigDict(frozen=True)

    output_path: str
    data_mode: Literal["synthetic_demo"]
    first_week: date
    latest_complete_week: date
    forecast_target_week: date
    taxonomy_version: str
    macro_families: int
    genres: int
    enabled_genres: int
    candidate_genres: int
    metric_rows: int
    forecast_rows: int
    next_up_rows: int
    brief_rows: int
    bluesky_receipts: int
    lastfm_snapshots: int
    musicbrainz_releases: int


@dataclass(frozen=True, slots=True)
class SourceRows:
    """Synthetic source and staging rows ready for parameterized inserts."""

    tag_mappings: tuple[SqlRow, ...]
    lastfm_snapshots: tuple[SqlRow, ...]
    bluesky_posts: tuple[SqlRow, ...]
    bluesky_engagement: tuple[SqlRow, ...]
    post_artist_links: tuple[SqlRow, ...]
    musicbrainz_releases: tuple[SqlRow, ...]


async def seed_demo_database(settings: DemoSettings) -> DemoSummary:
    """Create a complete demo artifact and return its verified row counts."""
    settings.output_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.output_path.exists():
        settings.output_path.unlink()

    computed_at = _computed_at(settings.as_of_date)
    weeks = _history_weeks(settings.as_of_date, settings.weeks)
    source_rows = _build_source_rows(weeks, computed_at)

    metric_store = DuckDBMetricStore(settings.output_path)
    await metric_store.initialize()
    _insert_source_rows(settings.output_path, source_rows)
    evidence = await metric_store.load_evidence()
    metrics = build_metrics(
        evidence,
        DEMO_GENRES,
        computed_at=computed_at,
        bootstrap_resamples=settings.bootstrap_resamples,
        bootstrap_seed=DEMO_SEED,
    )
    scene_points = _build_scene_points(metrics, weeks[-1], computed_at)
    metrics_with_scene = metrics.model_copy(
        update={"scene_map_points": scene_points}
    )
    await metric_store.replace(metrics_with_scene)

    forecasts = _build_forecasts(metrics_with_scene, weeks, computed_at)
    forecast_store = DuckDBForecastStore(settings.output_path)
    await forecast_store.initialize()
    await forecast_store.replace(forecasts)

    briefs = _build_briefs(metrics_with_scene, forecasts, computed_at)
    brief_store = DuckDBBriefStore(settings.output_path)
    await brief_store.initialize()
    await brief_store.replace(weeks[-1], briefs)

    _write_demo_manifest(
        settings.output_path,
        source_rows,
        metrics_with_scene,
        forecasts,
        briefs,
        computed_at,
    )
    _verify_demo_artifact(settings.output_path, weeks[-1])

    return DemoSummary(
        output_path=str(settings.output_path),
        data_mode="synthetic_demo",
        first_week=weeks[0],
        latest_complete_week=weeks[-1],
        forecast_target_week=weeks[-1] + timedelta(weeks=1),
        taxonomy_version=DEMO_TAXONOMY.taxonomy_version,
        macro_families=DEMO_MACRO_FAMILIES,
        genres=len(DEMO_GENRES),
        enabled_genres=sum(
            genre.status == "enabled" for genre in DEMO_GENRE_DEFINITIONS
        ),
        candidate_genres=sum(
            genre.status == "candidate" for genre in DEMO_GENRE_DEFINITIONS
        ),
        metric_rows=len(metrics_with_scene.genre_weeks),
        forecast_rows=len(forecasts.predictions),
        next_up_rows=len(forecasts.next_up),
        brief_rows=len(briefs),
        bluesky_receipts=len(source_rows.bluesky_posts),
        lastfm_snapshots=len(source_rows.lastfm_snapshots),
        musicbrainz_releases=len(source_rows.musicbrainz_releases),
    )


def _computed_at(as_of_date: date) -> datetime:
    return datetime.combine(as_of_date, time(hour=12), tzinfo=UTC)


def _history_weeks(as_of_date: date, count: int) -> tuple[date, ...]:
    current_monday = as_of_date - timedelta(days=as_of_date.weekday())
    latest_complete = current_monday - timedelta(weeks=1)
    return tuple(
        latest_complete - timedelta(weeks=count - index - 1)
        for index in range(count)
    )


def _build_source_rows(
    weeks: tuple[date, ...],
    computed_at: datetime,
) -> SourceRows:
    tag_mappings: list[SqlRow] = []
    lastfm_snapshots: list[SqlRow] = []
    bluesky_posts: list[SqlRow] = []
    bluesky_engagement: list[SqlRow] = []
    post_artist_links: list[SqlRow] = []
    musicbrainz_releases: list[SqlRow] = []

    for genre_index, genre in enumerate(DEMO_GENRES):
        for source_system in ("lastfm", "musicbrainz_genre"):
            tag_mappings.append(
                (
                    source_system,
                    genre,
                    genre,
                    1.0,
                    "demo_exact",
                    "synthetic_demo",
                    computed_at,
                )
            )

        artist_names = tuple(
            f"{_title(genre)} {suffix}" for suffix in ARTIST_SUFFIXES
        )
        artist_mbids = tuple(
            _synthetic_uuid(f"artist:{genre}:{artist_index}")
            for artist_index in range(len(artist_names))
        )
        cumulative_listeners = [
            8_000 + 430 * genre_index + 170 * artist_index
            for artist_index in range(len(artist_names))
        ]
        cumulative_plays = [
            210_000 + 9_000 * genre_index + 4_000 * artist_index
            for artist_index in range(len(artist_names))
        ]

        first_snapshot_at = _week_timestamp(
            weeks[0] - timedelta(weeks=1),
            day_offset=3,
            hour=12,
        )
        for artist_index, artist_name in enumerate(artist_names):
            lastfm_snapshots.append(
                (
                    artist_name,
                    artist_mbids[artist_index],
                    cumulative_listeners[artist_index],
                    cumulative_plays[artist_index],
                    [genre],
                    [genre],
                    first_snapshot_at,
                )
            )

        for week_index, week_start in enumerate(weeks):
            likes, reposts, replies = _conversation_totals(
                genre_index,
                week_index,
                len(weeks),
            )
            listener_delta, playcount_delta = _listening_totals(
                genre_index,
                week_index,
                len(weeks),
            )
            release_count = _release_count(
                genre_index,
                week_index,
                len(weeks),
            )

            like_parts = _partition(likes, len(POST_TEMPLATES))
            repost_parts = _partition(reposts, len(POST_TEMPLATES))
            reply_parts = _partition(replies, len(POST_TEMPLATES))
            for post_index, template in enumerate(POST_TEMPLATES):
                artist_index = post_index % len(artist_names)
                did = f"did:plc:synthetic{genre_index:02d}{post_index:02d}"
                record_key = (
                    f"demo{week_start.strftime('%Y%m%d')}"
                    f"{genre_index:02d}{post_index:02d}"
                )
                post_uri = f"at://{did}/app.bsky.feed.post/{record_key}"
                created_at = _week_timestamp(
                    week_start,
                    day_offset=1 + post_index,
                    hour=9 + post_index,
                )
                bluesky_posts.append(
                    (
                        post_uri,
                        did,
                        created_at,
                        template.format(artist=artist_names[artist_index]),
                        ["en"],
                        [],
                        ["demo", "nowplaying"],
                        ["intent:listening_to", "synthetic:demo"],
                        created_at + timedelta(minutes=2),
                    )
                )
                bluesky_engagement.append(
                    (
                        post_uri,
                        like_parts[post_index],
                        repost_parts[post_index],
                        reply_parts[post_index],
                        created_at + timedelta(hours=72),
                    )
                )
                post_artist_links.append(
                    (
                        post_uri,
                        artist_mbids[artist_index],
                        artist_names[artist_index],
                        "synthetic_direct_mbid",
                        100.0,
                        "mbid",
                        created_at + timedelta(minutes=3),
                    )
                )

            listener_parts = _partition(listener_delta, len(artist_names))
            playcount_parts = _partition(playcount_delta, len(artist_names))
            snapshot_at = _week_timestamp(
                week_start,
                day_offset=3,
                hour=12,
            )
            for artist_index, artist_name in enumerate(artist_names):
                cumulative_listeners[artist_index] += listener_parts[artist_index]
                cumulative_plays[artist_index] += playcount_parts[artist_index]
                lastfm_snapshots.append(
                    (
                        artist_name,
                        artist_mbids[artist_index],
                        cumulative_listeners[artist_index],
                        cumulative_plays[artist_index],
                        [genre],
                        [genre],
                        snapshot_at,
                    )
                )

            for release_index in range(release_count):
                artist_index = release_index % len(artist_names)
                release_mbid = _synthetic_uuid(
                    f"release:{genre}:{week_start}:{release_index}"
                )
                first_release_date = week_start + timedelta(
                    days=1 + release_index % 5
                )
                release_title = (
                    f"{RELEASE_WORDS[release_index % len(RELEASE_WORDS)]} "
                    f"{week_index + 1}"
                )
                musicbrainz_releases.append(
                    (
                        release_mbid,
                        release_title,
                        [
                            {
                                "credit_name": artist_names[artist_index],
                                "artist_name": artist_names[artist_index],
                                "mbid": artist_mbids[artist_index],
                                "join_phrase": "",
                            }
                        ],
                        [artist_mbids[artist_index]],
                        first_release_date.isoformat(),
                        ["Album" if release_index % 3 == 0 else "Single"],
                        [genre],
                        [],
                        computed_at,
                    )
                )

    return SourceRows(
        tag_mappings=tuple(tag_mappings),
        lastfm_snapshots=tuple(lastfm_snapshots),
        bluesky_posts=tuple(bluesky_posts),
        bluesky_engagement=tuple(bluesky_engagement),
        post_artist_links=tuple(post_artist_links),
        musicbrainz_releases=tuple(musicbrainz_releases),
    )


def _conversation_totals(
    genre_index: int,
    week_index: int,
    week_count: int,
) -> tuple[int, int, int]:
    phase = 2.0 * math.pi * genre_index / len(DEMO_GENRES)
    momentum = ((genre_index % 7) - 3) * week_index / max(week_count - 1, 1)
    seasonal = 7.0 * math.sin(week_index / 3.2 + phase)
    likes = max(6, round(28 + 2 * (genre_index % 6) + seasonal + momentum))
    reposts = max(2, round(7 + (genre_index % 5) + seasonal / 3.0 + momentum / 2.0))
    replies = max(1, round(4 + (genre_index % 4) + seasonal / 4.0))
    if week_index == week_count - 1 and genre_index in BREAKOUT_INDICES:
        likes = max(6, likes // 3)
        reposts = max(2, reposts // 3)
        replies = max(1, replies // 2)
    if week_index == week_count - 1 and genre_index in {2, 12, 24}:
        likes += 70
        reposts += 35
        replies += 14
    return likes, reposts, replies


def _listening_totals(
    genre_index: int,
    week_index: int,
    week_count: int,
) -> tuple[int, int]:
    phase = 2.0 * math.pi * genre_index / len(DEMO_GENRES)
    momentum = ((genre_index % 6) - 2) * 4.0 * week_index
    seasonal = 90.0 * math.cos(week_index / 4.3 + phase)
    listeners = max(
        30,
        round(135 + 11 * (genre_index % 8) + seasonal / 3.0 + momentum / 8.0),
    )
    plays = max(
        350,
        round(1_550 + 80 * (genre_index % 9) + seasonal * 3.0 + momentum),
    )
    if week_index == week_count - 1 and genre_index in BREAKOUT_INDICES:
        listeners += 1_100
        plays += 6_500
    return listeners, plays


def _release_count(
    genre_index: int,
    week_index: int,
    week_count: int,
) -> int:
    count = 1 + ((genre_index * 3 + week_index * 2) % 7)
    if week_index == week_count - 1 and genre_index in BREAKOUT_INDICES:
        return 1
    return count


def _insert_source_rows(database_path: Path, rows: SourceRows) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            _insert_many(
                connection,
                "upsert_stg_tag_genre_map.sql",
                rows.tag_mappings,
            )
            _insert_many(
                connection,
                "insert_raw_lastfm_artist_snapshots.sql",
                rows.lastfm_snapshots,
            )
            _insert_many(
                connection,
                "insert_raw_bluesky_posts.sql",
                rows.bluesky_posts,
            )
            _insert_many(
                connection,
                "insert_raw_bluesky_engagement.sql",
                rows.bluesky_engagement,
            )
            _insert_many(
                connection,
                "upsert_stg_post_artist_links.sql",
                rows.post_artist_links,
            )
            _insert_many(
                connection,
                "insert_raw_mb_release_groups.sql",
                rows.musicbrainz_releases,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _insert_many(
    connection: duckdb.DuckDBPyConnection,
    statement_name: str,
    rows: tuple[SqlRow, ...],
) -> None:
    if rows:
        connection.executemany(load_sql(statement_name), rows)


def _build_scene_points(
    metrics: MetricsBatch,
    latest_week: date,
    computed_at: datetime,
) -> tuple[SceneMapPoint, ...]:
    latest_rows = {
        row.canonical_genre: row
        for row in metrics.genre_weeks
        if row.week_start == latest_week
    }
    points: list[SceneMapPoint] = []
    for genre_index, genre in enumerate(DEMO_GENRES):
        metric = latest_rows[genre]
        angle = 2.0 * math.pi * genre_index / len(DEMO_GENRES)
        radius = 1.0 + 0.13 * (genre_index % 5)
        points.append(
            SceneMapPoint(
                as_of_week=latest_week,
                canonical_genre=genre,
                x=radius * math.cos(angle),
                y=radius * math.sin(angle),
                opportunity=metric.opportunity,
                opportunity_ci_low=metric.opportunity_ci_low,
                opportunity_ci_high=metric.opportunity_ci_high,
                discovery_gap=metric.discovery_gap,
                discovery_gap_ci_low=metric.discovery_gap_ci_low,
                discovery_gap_ci_high=metric.discovery_gap_ci_high,
                evidence_volume=(
                    len(metric.conversation_post_uris)
                    + len(metric.listening_artist_keys)
                    + len(metric.supply_release_group_mbids)
                ),
                computed_at=computed_at,
            )
        )
    return tuple(points)


def _build_forecasts(
    metrics: MetricsBatch,
    weeks: tuple[date, ...],
    computed_at: datetime,
) -> ForecastBatch:
    history = {
        (row.canonical_genre, row.week_start): row
        for row in metrics.genre_weeks
    }
    latest_week = weeks[-1]
    target_week = latest_week + timedelta(weeks=1)
    backtest_indices = tuple(range(8, len(weeks)))
    backtest_records: list[BacktestRecord] = []
    model_scores: list[ModelScore] = []
    predictions: list[ForecastPrediction] = []
    selected_predictions: dict[tuple[str, TargetAxis], ForecastPrediction] = {}

    for genre_index, genre in enumerate(DEMO_GENRES):
        no_skill = genre_index % 5 == 0
        for axis in ("conversation", "listening"):
            target_axis: TargetAxis = axis
            selected_model: ForecastModel = (
                "ets" if axis == "conversation" else "lightgbm"
            )
            naive_records = _synthetic_backtest_records(
                genre,
                target_axis,
                "naive",
                weeks,
                history,
                error_ratio=1.0,
            )
            backtest_records.extend(naive_records)
            naive_mae = _mean_absolute_error(naive_records)
            model_scores.append(
                ModelScore(
                    canonical_genre=genre,
                    target_axis=target_axis,
                    horizon=1,
                    model_name="naive",
                    backtest_start_week=weeks[backtest_indices[0]],
                    backtest_end_week=weeks[backtest_indices[-1]],
                    origin_count=len(naive_records),
                    mae=naive_mae,
                    naive_mae=naive_mae,
                    mase=1.0,
                    interval_coverage_80=0.83,
                    mean_interval_width=1.4,
                    score_status="scored",
                    evaluated_at=computed_at,
                )
            )

            selected_mase = 1.08 if no_skill else 0.58 + 0.04 * (genre_index % 5)
            if not no_skill:
                selected_records = _synthetic_backtest_records(
                    genre,
                    target_axis,
                    selected_model,
                    weeks,
                    history,
                    error_ratio=selected_mase,
                )
                backtest_records.extend(selected_records)
                model_scores.append(
                    ModelScore(
                        canonical_genre=genre,
                        target_axis=target_axis,
                        horizon=1,
                        model_name=selected_model,
                        backtest_start_week=weeks[backtest_indices[0]],
                        backtest_end_week=weeks[backtest_indices[-1]],
                        origin_count=len(selected_records),
                        mae=_mean_absolute_error(selected_records),
                        naive_mae=naive_mae,
                        mase=selected_mase,
                        interval_coverage_80=0.81,
                        mean_interval_width=1.1,
                        score_status="scored",
                        evaluated_at=computed_at,
                    )
                )

            latest_metric = history[(genre, latest_week)]
            latest_value = _axis_value(latest_metric, target_axis)
            growth = _forecast_growth(genre_index, target_axis)
            naive_prediction = ForecastPrediction(
                origin_week=latest_week,
                target_week=target_week,
                canonical_genre=genre,
                target_axis=target_axis,
                horizon=1,
                model_name="naive",
                is_naive_baseline=True,
                skill_status="no_skill" if no_skill else "baseline",
                prediction=latest_value,
                interval_low=latest_value - 0.75,
                interval_high=latest_value + 0.75,
                backtest_mase=1.0,
                backtest_coverage_80=0.83,
                backtest_origin_count=len(naive_records),
                training_start_week=weeks[0],
                training_end_week=latest_week,
                created_at=computed_at,
            )
            predictions.append(naive_prediction)
            if no_skill:
                selected_predictions[(genre, target_axis)] = naive_prediction
            else:
                skilled_prediction = ForecastPrediction(
                    origin_week=latest_week,
                    target_week=target_week,
                    canonical_genre=genre,
                    target_axis=target_axis,
                    horizon=1,
                    model_name=selected_model,
                    is_naive_baseline=False,
                    skill_status="skill",
                    prediction=latest_value + growth,
                    interval_low=latest_value + growth - 0.58,
                    interval_high=latest_value + growth + 0.58,
                    backtest_mase=selected_mase,
                    backtest_coverage_80=0.81,
                    backtest_origin_count=len(naive_records),
                    training_start_week=weeks[0],
                    training_end_week=latest_week,
                    created_at=computed_at,
                )
                predictions.append(skilled_prediction)
                selected_predictions[(genre, target_axis)] = skilled_prediction

    breakout_metrics = sorted(
        (
            row
            for row in metrics.genre_weeks
            if row.week_start == latest_week and row.breakout_precursor
        ),
        key=lambda row: (
            -(row.opportunity if row.opportunity is not None else -math.inf),
            row.canonical_genre,
        ),
    )
    next_up_candidates: list[NextUpPrediction] = []
    for metric in breakout_metrics:
        conversation = selected_predictions[(metric.canonical_genre, "conversation")]
        listening = selected_predictions[(metric.canonical_genre, "listening")]
        predicted_opportunity = (
            (conversation.prediction + listening.prediction) / 2.0
            - metric.supply_index
        )
        current_opportunity = metric.opportunity or 0.0
        predicted_gain = predicted_opportunity - current_opportunity
        next_up_candidates.append(
            NextUpPrediction(
                origin_week=latest_week,
                target_week=target_week,
                canonical_genre=metric.canonical_genre,
                rank=1,
                predicted_opportunity=predicted_opportunity,
                predicted_opportunity_interval_low=predicted_opportunity - 0.72,
                predicted_opportunity_interval_high=predicted_opportunity + 0.72,
                predicted_gain=predicted_gain,
                gain_interval_low=predicted_gain - 0.62,
                gain_interval_high=predicted_gain + 0.62,
                conversation_model=conversation.model_name,
                listening_model=listening.model_name,
                conversation_mase=conversation.backtest_mase,
                listening_mase=listening.backtest_mase,
                skill_status=(
                    "skill"
                    if conversation.skill_status == listening.skill_status == "skill"
                    else "no_skill"
                ),
                breakout_evidence_week=latest_week,
                created_at=computed_at,
            )
        )
    ranked_next_up = tuple(
        prediction.model_copy(update={"rank": rank})
        for rank, prediction in enumerate(
            sorted(
                next_up_candidates,
                key=lambda row: (-row.predicted_gain, row.canonical_genre),
            ),
            start=1,
        )
    )
    return ForecastBatch(
        backtest_records=tuple(backtest_records),
        model_scores=tuple(model_scores),
        predictions=tuple(predictions),
        next_up=ranked_next_up,
        history_week_count=len(weeks),
    )


def _synthetic_backtest_records(
    genre: str,
    target_axis: TargetAxis,
    model_name: ForecastModel,
    weeks: tuple[date, ...],
    history: dict[tuple[str, date], GenreWeekMetric],
    *,
    error_ratio: float,
) -> tuple[BacktestRecord, ...]:
    records: list[BacktestRecord] = []
    for target_index in range(8, len(weeks)):
        target_week = weeks[target_index]
        origin_week = weeks[target_index - 1]
        metric = history[(genre, target_week)]
        actual = _axis_value(metric, target_axis)
        base_error = 0.22 + 0.025 * (target_index % 5)
        signed_error = base_error * error_ratio * (-1.0 if target_index % 2 else 1.0)
        prediction = actual + signed_error
        width = max(0.52, abs(signed_error) + 0.18)
        records.append(
            BacktestRecord(
                canonical_genre=genre,
                target_axis=target_axis,
                horizon=1,
                model_name=model_name,
                origin_week=origin_week,
                target_week=target_week,
                training_start_week=weeks[0],
                training_end_week=origin_week,
                training_weeks=target_index,
                actual=actual,
                prediction=prediction,
                interval_low=prediction - width,
                interval_high=prediction + width,
                absolute_error=abs(signed_error),
                covered_80=True,
            )
        )
    return tuple(records)


def _axis_value(metric: GenreWeekMetric, target_axis: TargetAxis) -> float:
    value = getattr(metric, f"{target_axis}_index")
    if value is None:
        msg = f"demo metric lacks {target_axis} data"
        raise ValueError(msg)
    return float(value)


def _mean_absolute_error(records: tuple[BacktestRecord, ...]) -> float:
    return sum(record.absolute_error for record in records) / len(records)


def _forecast_growth(genre_index: int, target_axis: TargetAxis) -> float:
    growth = 0.08 + 0.05 * math.sin(genre_index)
    if genre_index in BREAKOUT_INDICES:
        growth += 0.28 if target_axis == "conversation" else 0.72
    return growth


def _build_briefs(
    metrics: MetricsBatch,
    forecasts: ForecastBatch,
    computed_at: datetime,
) -> tuple[GeneratedBrief, ...]:
    latest_week = max(row.week_start for row in metrics.genre_weeks)
    latest_metrics = {
        row.canonical_genre: row
        for row in metrics.genre_weeks
        if row.week_start == latest_week
    }
    skilled_rows = [
        row
        for row in forecasts.next_up
        if row.skill_status == "skill" and row.predicted_gain > 0
    ]
    if len(skilled_rows) < 3:
        skilled_rows = sorted(
            forecasts.next_up,
            key=lambda row: (-row.predicted_gain, row.canonical_genre),
        )
    briefs: list[GeneratedBrief] = []
    for row in skilled_rows[:4]:
        metric = latest_metrics[row.canonical_genre]
        opportunity = metric.opportunity
        opportunity_low = metric.opportunity_ci_low
        opportunity_high = metric.opportunity_ci_high
        if (
            opportunity is None
            or opportunity_low is None
            or opportunity_high is None
        ):
            continue
        genre_title = _title(row.canonical_genre)
        release_count = metric.supply_release_groups
        briefs.append(
            GeneratedBrief(
                brief_id=(
                    f"demo-{latest_week.isocalendar().year}-"
                    f"W{latest_week.isocalendar().week:02d}-"
                    f"{row.canonical_genre.replace(' ', '-')}"
                ),
                week_start=latest_week,
                canonical_genre=row.canonical_genre,
                headline=f"{genre_title} is opening before supply catches up",
                opportunity=opportunity,
                opportunity_ci_low=opportunity_low,
                opportunity_ci_high=opportunity_high,
                rationale=(
                    f"Synthetic demo evidence puts {genre_title} above its "
                    f"weekly demand baseline while only {release_count} release "
                    f"{'group was' if release_count == 1 else 'groups were'} "
                    "observed. Listening is accelerating ahead of conversation, "
                    "leaving room for a distinct creator voice."
                ),
                recommended_actions=(
                    "Build around the scene's pacing without copying its dominant texture.",
                    "Test one concise release concept before committing to a full sequence.",
                    "Use the linked synthetic receipts to inspect how the evidence panel behaves.",
                ),
                evidence_uris=(
                    *metric.conversation_post_uris[:2],
                    *metric.supply_release_group_mbids[:1],
                ),
                created_at=computed_at,
            )
        )
    return tuple(briefs)


def _write_demo_manifest(
    database_path: Path,
    source_rows: SourceRows,
    metrics: MetricsBatch,
    forecasts: ForecastBatch,
    briefs: tuple[GeneratedBrief, ...],
    computed_at: datetime,
) -> None:
    run_id = f"synthetic-demo-{computed_at.date().isoformat()}"
    started_at = computed_at - timedelta(seconds=42)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_mart_pipeline_runs.sql"))
        connection.execute(
            load_sql("insert_pipeline_run_started.sql"),
            (
                run_id,
                "weekly",
                "synthetic_demo",
                "synthetic",
                started_at,
            ),
        )
        connection.execute(
            load_sql("update_pipeline_run_finished.sql"),
            (
                "success",
                computed_at,
                42.0,
                len(source_rows.bluesky_posts),
                len(source_rows.bluesky_engagement),
                0,
                len(source_rows.lastfm_snapshots),
                len(source_rows.musicbrainz_releases),
                len(source_rows.bluesky_posts),
                len(source_rows.post_artist_links),
                1.0,
                len(metrics.genre_weeks),
                len(forecasts.predictions),
                len(briefs),
                None,
                run_id,
            ),
        )


def _verify_demo_artifact(database_path: Path, latest_week: date) -> None:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            load_sql("summarize_demo_artifact.sql"),
            (
                latest_week,
                latest_week,
                latest_week,
                latest_week,
                latest_week,
                latest_week,
            ),
        ).fetchone()
    if row is None:
        msg = "demo verification returned no result"
        raise RuntimeError(msg)
    (
        opportunity_rows,
        history_rows,
        ecosystem_rows,
        forecast_rows,
        next_up_rows,
        brief_rows,
        scene_rows,
        conversation_receipts,
        listening_receipts,
        supply_receipts,
        trigger_name,
    ) = row
    expected_genres = len(DEMO_GENRES)
    checks = {
        "opportunities": opportunity_rows >= expected_genres,
        "history": history_rows >= expected_genres,
        "ecosystem": ecosystem_rows > 0,
        "forecasts": forecast_rows > 0,
        "next_up": next_up_rows > 0,
        "briefs": brief_rows > 0,
        "scene_map": scene_rows == expected_genres,
        "conversation_receipts": conversation_receipts > 0,
        "listening_receipts": listening_receipts > 0,
        "supply_receipts": supply_receipts > 0,
        "manifest": trigger_name == "synthetic_demo",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        msg = f"demo artifact is incomplete: {', '.join(failed)}"
        raise RuntimeError(msg)


def _partition(total: int, parts: int) -> tuple[int, ...]:
    quotient, remainder = divmod(total, parts)
    return tuple(
        quotient + (1 if index < remainder else 0)
        for index in range(parts)
    )


def _week_timestamp(
    week_start: date,
    *,
    day_offset: int,
    hour: int,
) -> datetime:
    event_date = week_start + timedelta(days=day_offset)
    return datetime.combine(event_date, time(hour=hour), tzinfo=UTC)


def _synthetic_uuid(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-"
        f"{digest[16:20]}-{digest[20:32]}"
    )


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def _parse_args() -> DemoSettings:
    parser = argparse.ArgumentParser(
        description="Create an isolated synthetic Soundcheck DuckDB artifact.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Demo DuckDB output path.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="UTC artifact date in YYYY-MM-DD form.",
    )
    parser.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=DEFAULT_BOOTSTRAP_RESAMPLES,
    )
    arguments = parser.parse_args()
    return DemoSettings(
        output_path=arguments.output,
        as_of_date=arguments.as_of,
        weeks=arguments.weeks,
        bootstrap_resamples=arguments.bootstrap_resamples,
    )


def main() -> None:
    """Generate the demo database and print one JSON summary."""
    summary = asyncio.run(seed_demo_database(_parse_args()))
    print(json.dumps(summary.model_dump(mode="json"), sort_keys=True))


if __name__ == "__main__":
    main()
