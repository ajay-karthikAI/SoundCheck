"""DuckDB storage for incremental entity resolution."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.resolve.entities import (
    LastfmArtistCandidate,
    RawResolutionPost,
    ResolutionBatch,
)
from soundcheck.sql.loader import load_sql


class DuckDBEntityResolutionStore:
    """Load unresolved raw posts and atomically persist staged outcomes."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_pending_posts(self) -> tuple[RawResolutionPost, ...]:
        return await asyncio.to_thread(_load_pending_posts, self._database_path)

    async def load_lastfm_artists(self) -> tuple[LastfmArtistCandidate, ...]:
        return await asyncio.to_thread(_load_lastfm_artists, self._database_path)

    async def persist(self, batch: ResolutionBatch) -> tuple[int, int, int]:
        await asyncio.to_thread(_persist, self._database_path, batch)
        return len(batch.links), len(batch.ambiguities), len(batch.attempts)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_raw_lastfm_snapshots.sql"))
        connection.execute(load_sql("create_raw_mb_release_groups.sql"))
        connection.execute(load_sql("create_stg_post_artist_resolution.sql"))


def _load_pending_posts(database_path: Path) -> tuple[RawResolutionPost, ...]:
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_pending_resolution_posts.sql")
            ).fetchall()
    except duckdb.CatalogException:
        return ()
    return tuple(
        RawResolutionPost(uri=row[0], text=row[1], link_urls=tuple(row[2]))
        for row in rows
    )


def _load_lastfm_artists(
    database_path: Path,
) -> tuple[LastfmArtistCandidate, ...]:
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            rows = connection.execute(
                load_sql("select_latest_lastfm_artist_catalog.sql")
            ).fetchall()
    except duckdb.CatalogException:
        return ()
    return tuple(
        LastfmArtistCandidate(artist_name=row[0], mbid=row[1])
        for row in rows
    )


def _persist(database_path: Path, batch: ResolutionBatch) -> None:
    link_rows = [
        (
            link.post_uri,
            link.artist_mbid,
            link.artist_name_raw,
            link.method,
            link.score,
            link.join_key_type,
            link.resolved_at,
        )
        for link in batch.links
    ]
    ambiguity_rows = [
        (
            ambiguity.post_uri,
            ambiguity.artist_name_raw,
            ambiguity.top_artist_mbid,
            ambiguity.top_artist_name,
            ambiguity.top_score,
            ambiguity.second_artist_mbid,
            ambiguity.second_artist_name,
            ambiguity.second_score,
            ambiguity.reason,
            ambiguity.resolved_at,
        )
        for ambiguity in batch.ambiguities
    ]
    attempt_rows = [
        (
            attempt.post_uri,
            attempt.outcome,
            attempt.candidate_count,
            attempt.attempted_at,
        )
        for attempt in batch.attempts
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            if link_rows:
                connection.executemany(
                    load_sql("upsert_stg_post_artist_links.sql"),
                    link_rows,
                )
            if ambiguity_rows:
                connection.executemany(
                    load_sql("upsert_stg_post_artist_ambiguities.sql"),
                    ambiguity_rows,
                )
            if attempt_rows:
                connection.executemany(
                    load_sql("insert_stg_post_artist_attempts.sql"),
                    attempt_rows,
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
