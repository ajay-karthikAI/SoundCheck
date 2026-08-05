"""DuckDB I/O for evidence reads and atomic metrics-mart replacement."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.metrics.models import (
    CanonicalGenreEmbedding,
    ConversationEvidence,
    EcosystemWeekMetric,
    GenreWeekMetric,
    ListeningDeltaCandidate,
    MetricEvidence,
    MetricsBatch,
    SceneMapPoint,
    SupplyEvidence,
)
from soundcheck.sql.loader import load_sql


class DuckDBMetricStore:
    """Read immutable evidence and replace derived marts idempotently."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_evidence(self) -> MetricEvidence:
        return await asyncio.to_thread(_load_evidence, self._database_path)

    async def load_scene_embeddings(
        self,
    ) -> tuple[CanonicalGenreEmbedding, ...]:
        return await asyncio.to_thread(
            _load_scene_embeddings,
            self._database_path,
        )

    async def replace(self, batch: MetricsBatch) -> tuple[int, int]:
        await asyncio.to_thread(_replace, self._database_path, batch)
        return len(batch.genre_weeks), len(batch.ecosystem_weeks)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement_name in (
            "create_raw_bluesky_posts.sql",
            "create_raw_bluesky_engagement.sql",
            "create_raw_lastfm_snapshots.sql",
            "create_raw_mb_release_groups.sql",
            "create_stg_post_artist_resolution.sql",
            "create_stg_genre_resolution.sql",
            "create_mart_metrics.sql",
            "create_mart_evidence.sql",
            "create_mart_bluesky_music_feed.sql",
            "create_mart_scene_map.sql",
            "create_mart_briefs.sql",
            "create_mart_pipeline_runs.sql",
        ):
            connection.execute(load_sql(statement_name))


def _load_evidence(database_path: Path) -> MetricEvidence:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        conversation_rows = connection.execute(
            load_sql("select_metric_conversation_evidence.sql")
        ).fetchall()
        listening_rows = connection.execute(
            load_sql("select_metric_listening_delta_candidates.sql")
        ).fetchall()
        supply_rows = connection.execute(
            load_sql("select_metric_supply_evidence.sql")
        ).fetchall()
    return MetricEvidence(
        conversation=tuple(
            ConversationEvidence(
                week_start=row[0],
                canonical_genre=row[1],
                post_uri=row[2],
                mentions=row[3],
                likes=row[4],
                reposts=row[5],
                replies=row[6],
            )
            for row in conversation_rows
        ),
        listening_candidates=tuple(
            ListeningDeltaCandidate(
                week_start=row[0],
                canonical_genre=row[1],
                artist_key=row[2],
                artist_name=row[3],
                playcount=row[4],
                listeners=row[5],
                previous_playcount=row[6],
                previous_listeners=row[7],
            )
            for row in listening_rows
        ),
        supply=tuple(
            SupplyEvidence(
                week_start=row[0],
                canonical_genre=row[1],
                release_group_mbid=row[2],
            )
            for row in supply_rows
        ),
    )


def _load_scene_embeddings(
    database_path: Path,
) -> tuple[CanonicalGenreEmbedding, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_canonical_genre_embeddings.sql")
        ).fetchall()
    return tuple(
        CanonicalGenreEmbedding(
            canonical_genre=row[0],
            embedding=tuple(float(value) for value in row[1]),
        )
        for row in rows
    )


def _replace(database_path: Path, batch: MetricsBatch) -> None:
    genre_rows = [_genre_row(metric) for metric in batch.genre_weeks]
    ecosystem_rows = [_ecosystem_row(metric) for metric in batch.ecosystem_weeks]
    scene_map_rows = [_scene_map_row(point) for point in batch.scene_map_points]
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            connection.execute(load_sql("delete_mart_metrics.sql"))
            if genre_rows:
                connection.executemany(
                    load_sql("insert_mart_genre_weekly.sql"),
                    genre_rows,
                )
            if ecosystem_rows:
                connection.executemany(
                    load_sql("insert_mart_ecosystem_weekly.sql"),
                    ecosystem_rows,
                )
            if scene_map_rows:
                connection.executemany(
                    load_sql("insert_mart_scene_map.sql"),
                    scene_map_rows,
                )
            connection.execute(load_sql("refresh_mart_evidence.sql"))
            connection.execute(
                load_sql("refresh_mart_bluesky_music_feed.sql")
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _genre_row(metric: GenreWeekMetric) -> tuple[object, ...]:
    return (
        metric.week_start,
        metric.iso_year,
        metric.iso_week,
        metric.canonical_genre,
        metric.conversation_mentions,
        metric.conversation_likes,
        metric.conversation_reposts,
        metric.conversation_replies,
        metric.conversation_score_raw,
        metric.conversation_score_shrunk,
        metric.conversation_share_raw,
        metric.conversation_share_shrunk,
        metric.conversation_prior_share,
        metric.conversation_effective_n,
        metric.conversation_shrinkage_weight,
        metric.listening_playcount_delta,
        metric.listening_listeners_delta,
        metric.listening_score_raw,
        metric.supply_release_groups,
        metric.supply_rate_shrunk,
        metric.supply_prior_mean,
        metric.supply_effective_n,
        metric.supply_shrinkage_weight,
        metric.conversation_index,
        metric.conversation_index_ci_low,
        metric.conversation_index_ci_high,
        metric.listening_index,
        metric.listening_index_ci_low,
        metric.listening_index_ci_high,
        metric.supply_index,
        metric.supply_index_ci_low,
        metric.supply_index_ci_high,
        metric.opportunity,
        metric.opportunity_ci_low,
        metric.opportunity_ci_high,
        metric.discovery_gap,
        metric.discovery_gap_ci_low,
        metric.discovery_gap_ci_high,
        metric.conversation_ewma,
        metric.conversation_ewma_ci_low,
        metric.conversation_ewma_ci_high,
        metric.listening_ewma,
        metric.listening_ewma_ci_low,
        metric.listening_ewma_ci_high,
        metric.supply_ewma,
        metric.supply_ewma_ci_low,
        metric.supply_ewma_ci_high,
        metric.conversation_spike,
        metric.listening_spike,
        metric.supply_spike,
        metric.breakout_precursor,
        list(metric.conversation_post_uris),
        list(metric.listening_artist_keys),
        list(metric.supply_release_group_mbids),
        metric.computed_at,
    )


def _ecosystem_row(metric: EcosystemWeekMetric) -> tuple[object, ...]:
    return (
        metric.week_start,
        metric.iso_year,
        metric.iso_week,
        metric.shannon_listening_entropy,
        metric.shannon_listening_entropy_ci_low,
        metric.shannon_listening_entropy_ci_high,
        metric.effective_genres,
        metric.effective_genres_ci_low,
        metric.effective_genres_ci_high,
        metric.conversation_hhi,
        metric.conversation_hhi_ci_low,
        metric.conversation_hhi_ci_high,
        metric.listening_top10_share,
        metric.listening_top10_share_ci_low,
        metric.listening_top10_share_ci_high,
        metric.scene_churn_jaccard_4w,
        metric.scene_churn_jaccard_4w_ci_low,
        metric.scene_churn_jaccard_4w_ci_high,
        list(metric.breakout_genres),
        metric.canonical_genre_count,
        metric.listening_observed_genres,
        metric.opportunity_observed_genres,
        metric.computed_at,
    )


def _scene_map_row(
    point: SceneMapPoint,
) -> tuple[object, ...]:
    return (
        point.as_of_week,
        point.canonical_genre,
        point.x,
        point.y,
        point.opportunity,
        point.opportunity_ci_low,
        point.opportunity_ci_high,
        point.discovery_gap,
        point.discovery_gap_ci_low,
        point.discovery_gap_ci_high,
        point.evidence_volume,
        point.computed_at,
    )
