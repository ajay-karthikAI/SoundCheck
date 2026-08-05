"""DuckDB evidence loading and version-isolated taxonomy-v2 metric writes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.metrics.coverage_storage import load_coverage_rows
from soundcheck.metrics.v2_models import (
    ConversationEvidenceV2,
    ConversationReceiptV2,
    EcosystemWeekV2,
    GenreWeekV2,
    ListeningCandidateV2,
    ListeningReceiptV2,
    MacroFamilyWeekV2,
    MetricEstimateV2,
    MetricEvidenceV2,
    MetricsV2Batch,
    SupplyEvidenceV2,
    SupplyReceiptV2,
)
from soundcheck.sql.loader import load_sql


class DuckDBMetricV2Store:
    """Keep one taxonomy version replaceable without touching v1 or other versions."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_evidence(self, taxonomy_version: str) -> MetricEvidenceV2:
        return await asyncio.to_thread(
            _load_evidence,
            self._database_path,
            taxonomy_version,
        )

    async def replace(self, batch: MetricsV2Batch) -> None:
        await asyncio.to_thread(_replace, self._database_path, batch)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement in (
            "create_raw_bluesky_posts.sql",
            "create_raw_bluesky_engagement.sql",
            "create_raw_lastfm_snapshots.sql",
            "create_raw_mb_release_groups.sql",
            "create_stg_post_artist_resolution.sql",
            "create_stg_genre_resolution_v2.sql",
            "create_mart_genre_coverage_v2.sql",
            "create_mart_metrics_v2.sql",
            "create_mart_evidence_v2.sql",
            "create_mart_briefs.sql",
            "create_mart_scene_map.sql",
        ):
            connection.execute(load_sql(statement))


def _load_evidence(
    database_path: Path,
    taxonomy_version: str,
) -> MetricEvidenceV2:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        conversation_rows = connection.execute(
            load_sql("select_metric_v2_conversation_evidence.sql"),
            [taxonomy_version],
        ).fetchall()
        listening_rows = connection.execute(
            load_sql("select_metric_v2_listening_candidates.sql"),
            [taxonomy_version],
        ).fetchall()
        supply_rows = connection.execute(
            load_sql("select_metric_v2_supply_evidence.sql"),
            [taxonomy_version],
        ).fetchall()
    return MetricEvidenceV2(
        taxonomy_version=taxonomy_version,
        conversation=tuple(
            ConversationEvidenceV2(
                week_start=row[0],
                genre_id=row[1],
                macro_family_id=row[2],
                post_uri=row[3],
                membership_weight=row[4],
                likes=row[5],
                reposts=row[6],
                replies=row[7],
                did=row[8],
                created_at=row[9],
                text=row[10],
                artist_name_raw=row[11],
                resolution_method=row[12],
                resolution_score=row[13],
                join_key_type=row[14],
                membership_method=row[15],
                membership_confidence=row[16],
            )
            for row in conversation_rows
        ),
        listening_candidates=tuple(
            ListeningCandidateV2(
                week_start=row[0],
                genre_id=row[1],
                macro_family_id=row[2],
                artist_key=row[3],
                membership_weight=row[4],
                playcount=row[5],
                listeners=row[6],
                previous_playcount=row[7],
                previous_listeners=row[8],
                artist_name=row[9],
                artist_mbid=row[10],
                fetched_at=row[11],
                previous_fetched_at=row[12],
                membership_method=row[13],
                membership_confidence=row[14],
            )
            for row in listening_rows
        ),
        supply=tuple(
            SupplyEvidenceV2(
                week_start=row[0],
                genre_id=row[1],
                macro_family_id=row[2],
                release_group_mbid=row[3],
                membership_weight=row[4],
                title=row[5],
                artist_credits=tuple(row[6]),
                first_release_date=row[7],
                types=tuple(row[8]),
                genres=tuple(row[9]),
                fetched_at=row[10],
            )
            for row in supply_rows
        ),
        coverage=load_coverage_rows(database_path, taxonomy_version),
    )


def _genre_row(row: GenreWeekV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.iso_year,
        row.iso_week,
        row.genre_id,
        row.display_name,
        row.macro_family_id,
        row.parent_genre_id,
        row.coverage_state,
        row.estimate_status,
        row.estimate_eligible,
        row.conversation_score_raw,
        row.listening_playcount_delta,
        row.listening_listeners_delta,
        row.listening_score_raw,
        row.supply_release_groups_raw,
        row.conversation_score_shrunk,
        row.conversation_effective_n,
        row.conversation_subgenre_shrinkage_weight,
        row.conversation_family_shrinkage_weight,
        row.conversation_combined_shrinkage_weight,
        row.listening_effective_n,
        row.listening_shrinkage_weight,
        row.supply_rate_shrunk,
        row.supply_family_prior_mean,
        row.supply_global_prior_mean,
        row.supply_effective_n,
        row.supply_subgenre_shrinkage_weight,
        row.supply_family_shrinkage_weight,
        row.supply_combined_shrinkage_weight,
        row.breakout_global,
        row.breakout_peer_family,
        list(row.conversation_post_uris),
        list(row.listening_artist_keys),
        list(row.supply_release_group_mbids),
        row.computed_at,
    )


def _estimate_row(row: MetricEstimateV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.scope_type,
        row.scope_id,
        row.macro_family_id,
        row.context,
        row.metric_name,
        row.estimate_status,
        row.estimate,
        row.ci_low,
        row.ci_high,
        row.ewma,
        row.ewma_ci_low,
        row.ewma_ci_high,
        row.spike,
        row.computed_at,
    )


def _macro_row(row: MacroFamilyWeekV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.iso_year,
        row.iso_week,
        row.macro_family_id,
        row.display_name,
        row.total_genres,
        row.eligible_genres,
        row.estimate_status,
        row.coverage_state_counts_json,
        row.conversation_score_raw,
        row.listening_score_raw,
        row.supply_release_groups_raw,
        row.conversation_effective_n,
        row.listening_effective_n,
        row.supply_effective_n,
        list(row.breakout_genres_global),
        list(row.breakout_genres_peer),
        row.computed_at,
    )


def _ecosystem_row(row: EcosystemWeekV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.iso_year,
        row.iso_week,
        row.scope_type,
        row.scope_id,
        row.estimate_status,
        row.listening_entropy,
        row.listening_entropy_ci_low,
        row.listening_entropy_ci_high,
        row.effective_genres,
        row.effective_genres_ci_low,
        row.effective_genres_ci_high,
        row.conversation_hhi,
        row.conversation_hhi_ci_low,
        row.conversation_hhi_ci_high,
        row.listening_top_share,
        row.listening_top_share_ci_low,
        row.listening_top_share_ci_high,
        row.listening_top_share_k,
        row.churn_jaccard_4w,
        row.churn_jaccard_4w_ci_low,
        row.churn_jaccard_4w_ci_high,
        list(row.breakout_genres),
        row.eligible_genres,
        row.computed_at,
    )


def _conversation_receipt_row(
    row: ConversationReceiptV2,
) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.genre_id,
        row.macro_family_id,
        row.post_uri,
        row.did,
        row.created_at,
        row.text,
        row.likes,
        row.reposts,
        row.replies,
        row.artist_name_raw,
        row.resolution_method,
        row.resolution_score,
        row.join_key_type,
        row.membership_weight,
        row.membership_method,
        row.membership_confidence,
    )


def _listening_receipt_row(
    row: ListeningReceiptV2,
) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.genre_id,
        row.macro_family_id,
        row.artist_key,
        row.artist_name,
        row.artist_mbid,
        row.playcount,
        row.listeners,
        row.previous_playcount,
        row.previous_listeners,
        row.playcount_delta,
        row.listeners_delta,
        row.fetched_at,
        row.previous_fetched_at,
        row.membership_weight,
        row.membership_method,
        row.membership_confidence,
    )


def _supply_receipt_row(row: SupplyReceiptV2) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.genre_id,
        row.macro_family_id,
        row.release_group_mbid,
        row.title,
        list(row.artist_credits),
        row.first_release_date,
        list(row.types),
        list(row.genres),
        row.fetched_at,
        row.membership_weight,
    )


def _replace(database_path: Path, batch: MetricsV2Batch) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            for statement in (
                "delete_mart_conversation_evidence_v2_version.sql",
                "delete_mart_listening_evidence_v2_version.sql",
                "delete_mart_supply_evidence_v2_version.sql",
                "delete_mart_metric_estimates_v2_version.sql",
                "delete_mart_ecosystem_weekly_v2_version.sql",
                "delete_mart_macro_family_weekly_v2_version.sql",
                "delete_mart_genre_weekly_v2_version.sql",
            ):
                connection.execute(
                    load_sql(statement),
                    [batch.taxonomy_version],
                )
            if batch.genre_weeks:
                connection.executemany(
                    load_sql("insert_mart_genre_weekly_v2.sql"),
                    [_genre_row(row) for row in batch.genre_weeks],
                )
            if batch.macro_family_weeks:
                connection.executemany(
                    load_sql("insert_mart_macro_family_weekly_v2.sql"),
                    [_macro_row(row) for row in batch.macro_family_weeks],
                )
            if batch.estimates:
                connection.executemany(
                    load_sql("insert_mart_metric_estimate_v2.sql"),
                    [_estimate_row(row) for row in batch.estimates],
                )
            if batch.ecosystem_weeks:
                connection.executemany(
                    load_sql("insert_mart_ecosystem_weekly_v2.sql"),
                    [_ecosystem_row(row) for row in batch.ecosystem_weeks],
                )
            if batch.conversation_evidence:
                connection.executemany(
                    load_sql("insert_mart_conversation_evidence_v2.sql"),
                    [
                        _conversation_receipt_row(row)
                        for row in batch.conversation_evidence
                    ],
                )
            if batch.listening_evidence:
                connection.executemany(
                    load_sql("insert_mart_listening_evidence_v2.sql"),
                    [
                        _listening_receipt_row(row)
                        for row in batch.listening_evidence
                    ],
                )
            if batch.supply_evidence:
                connection.executemany(
                    load_sql("insert_mart_supply_evidence_v2.sql"),
                    [
                        _supply_receipt_row(row)
                        for row in batch.supply_evidence
                    ],
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
