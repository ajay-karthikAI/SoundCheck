"""DuckDB reads and atomic persistence for template-based creator briefs."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import duckdb

from soundcheck.briefs.models import (
    BriefArtistEvidence,
    BriefCandidate,
    BriefConversationEvidence,
    BriefEvidence,
    BriefReleaseEvidence,
    BriefSceneGenre,
    BriefSourceBundle,
    GeneratedBrief,
)
from soundcheck.sql.loader import load_sql


class DuckDBBriefStore:
    """Read precomputed inputs and replace one genre-week brief batch."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def latest_complete_week(self) -> date | None:
        return await asyncio.to_thread(
            _latest_complete_week,
            self._database_path,
        )

    async def load_sources(self, week_start: date) -> BriefSourceBundle:
        return await asyncio.to_thread(
            _load_sources,
            self._database_path,
            week_start,
        )

    async def replace(
        self,
        week_start: date,
        briefs: tuple[GeneratedBrief, ...],
    ) -> int:
        await asyncio.to_thread(
            _replace,
            self._database_path,
            week_start,
            briefs,
        )
        return len(briefs)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement_name in (
            "create_stg_genre_resolution.sql",
            "create_mart_metrics.sql",
            "create_mart_metrics_v2.sql",
            "create_mart_metric_versions.sql",
            "create_mart_evidence.sql",
            "create_fcst_tables.sql",
            "create_mart_briefs.sql",
            "create_mart_pipeline_runs.sql",
        ):
            connection.execute(load_sql(statement_name))


def _latest_complete_week(database_path: Path) -> date | None:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            load_sql("api_latest_complete_week.sql")
        ).fetchone()
    return None if row is None else row[0]


def _load_sources(
    database_path: Path,
    week_start: date,
) -> BriefSourceBundle:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        candidate_rows = connection.execute(
            load_sql("select_brief_candidates.sql"),
            (week_start,),
        ).fetchall()
        candidates = tuple(_candidate(row) for row in candidate_rows)
        evidence_by_genre: dict[str, BriefEvidence] = {}
        for candidate in candidates:
            genre = candidate.canonical_genre
            artist_rows = connection.execute(
                load_sql("select_brief_artists.sql"),
                (week_start, genre, 3),
            ).fetchall()
            conversation_row = connection.execute(
                load_sql("select_brief_conversation.sql"),
                (week_start, genre),
            ).fetchone()
            release_rows = connection.execute(
                load_sql("select_brief_releases.sql"),
                (week_start, genre, 2),
            ).fetchall()
            evidence_by_genre[genre] = BriefEvidence(
                artists=tuple(
                    BriefArtistEvidence(
                        artist_key=row[0],
                        artist_name=row[1],
                        artist_mbid=row[2],
                        playcount_delta=row[3],
                        listeners_delta=row[4],
                        weighted_delta=row[5],
                    )
                    for row in artist_rows
                ),
                conversation=(
                    None
                    if conversation_row is None
                    else BriefConversationEvidence(
                        post_uri=conversation_row[0],
                        did=conversation_row[1],
                        text=conversation_row[2],
                        weighted_score=conversation_row[3],
                    )
                ),
                releases=tuple(
                    BriefReleaseEvidence(
                        release_group_mbid=row[0],
                        title=row[1],
                    )
                    for row in release_rows
                ),
            )
        scene_rows = connection.execute(
            load_sql("select_brief_scene_context.sql"),
            (week_start,),
        ).fetchall()
    return BriefSourceBundle(
        candidates=candidates,
        evidence_by_genre=evidence_by_genre,
        scene_genres=tuple(
            BriefSceneGenre(
                canonical_genre=row[0],
                embedding=tuple(float(value) for value in row[1]),
                supply_index=row[2],
                supply_release_groups=row[3],
            )
            for row in scene_rows
        ),
    )


def _candidate(row: tuple[object, ...]) -> BriefCandidate:
    return BriefCandidate.model_validate(
        {
            "week_start": row[0],
            "canonical_genre": row[1],
            "opportunity": row[2],
            "opportunity_ci_low": row[3],
            "opportunity_ci_high": row[4],
            "conversation_effective_n": row[5],
            "supply_effective_n": row[6],
            "supply_release_groups": row[7],
            "typical_releases": row[8],
            "release_range_low": row[9],
            "release_range_high": row[10],
            "release_history_weeks": row[11],
            "target_week": row[12],
            "predicted_gain": row[13],
            "gain_interval_low": row[14],
            "gain_interval_high": row[15],
            "predicted_opportunity": row[16],
            "predicted_opportunity_interval_low": row[17],
            "predicted_opportunity_interval_high": row[18],
            "skill_status": row[19],
        }
    )


def _replace(
    database_path: Path,
    week_start: date,
    briefs: tuple[GeneratedBrief, ...],
) -> None:
    rows = [
        (
            brief.brief_id,
            brief.week_start,
            brief.canonical_genre,
            brief.headline,
            brief.opportunity,
            brief.opportunity_ci_low,
            brief.opportunity_ci_high,
            brief.rationale,
            list(brief.recommended_actions),
            list(brief.evidence_uris),
            brief.created_at,
        )
        for brief in briefs
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            connection.execute(
                load_sql("delete_mart_briefs_for_week.sql"),
                (week_start,),
            )
            if rows:
                connection.executemany(
                    load_sql("insert_mart_brief.sql"),
                    rows,
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
