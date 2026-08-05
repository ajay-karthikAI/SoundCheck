"""DuckDB persistence for immutable Last.fm observations."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from soundcheck.ingest.lastfm.models import (
    LastfmArtistSnapshot,
    LastfmTagSnapshot,
)
from soundcheck.sql.loader import load_sql


class LastfmSnapshotWriter:
    """Append complete Last.fm collection runs without updates."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        """Create both raw snapshot tables."""
        await asyncio.to_thread(_initialize, self._database_path)

    async def append(
        self,
        tag_snapshots: Sequence[LastfmTagSnapshot],
        artist_snapshots: Sequence[LastfmArtistSnapshot],
    ) -> tuple[int, int]:
        """Atomically append one run's tag and artist observations."""
        await asyncio.to_thread(
            _append_snapshots,
            self._database_path,
            tuple(tag_snapshots),
            tuple(artist_snapshots),
        )
        return len(tag_snapshots), len(artist_snapshots)

    async def append_checkpointed(
        self,
        run_key: str,
        tag_snapshots: Sequence[LastfmTagSnapshot],
        artist_snapshots: Sequence[LastfmArtistSnapshot],
    ) -> tuple[int, int]:
        """Atomically append one run and its completion marker exactly once."""

        await asyncio.to_thread(
            _append_checkpointed,
            self._database_path,
            run_key,
            tuple(tag_snapshots),
            tuple(artist_snapshots),
        )
        return len(tag_snapshots), len(artist_snapshots)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_raw_lastfm_snapshots.sql"))
        connection.execute(load_sql("create_stg_collection_checkpoints.sql"))


def _append_snapshots(
    database_path: Path,
    tag_snapshots: Sequence[LastfmTagSnapshot],
    artist_snapshots: Sequence[LastfmArtistSnapshot],
) -> None:
    tag_rows = _tag_rows(tag_snapshots)
    artist_rows = _artist_rows(artist_snapshots)
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            _insert_rows(connection, tag_rows, artist_rows)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _tag_rows(
    tag_snapshots: Sequence[LastfmTagSnapshot],
) -> list[tuple[object, ...]]:
    return [
        (
            snapshot.tag,
            snapshot.reach,
            snapshot.total,
            [
                {"name": artist.name, "mbid": artist.mbid, "rank": artist.rank}
                for artist in snapshot.top_artists
            ],
            [
                {
                    "title": album.title,
                    "mbid": album.mbid,
                    "artist_name": album.artist_name,
                    "artist_mbid": album.artist_mbid,
                    "rank": album.rank,
                }
                for album in snapshot.top_albums
            ],
            snapshot.fetched_at,
        )
        for snapshot in tag_snapshots
    ]


def _artist_rows(
    artist_snapshots: Sequence[LastfmArtistSnapshot],
) -> list[tuple[object, ...]]:
    return [
        (
            snapshot.artist_name,
            snapshot.mbid,
            snapshot.listeners,
            snapshot.playcount,
            list(snapshot.tags),
            list(snapshot.source_genres),
            snapshot.fetched_at,
        )
        for snapshot in artist_snapshots
    ]


def _insert_rows(
    connection: duckdb.DuckDBPyConnection,
    tag_rows: Sequence[tuple[object, ...]],
    artist_rows: Sequence[tuple[object, ...]],
) -> None:
    if tag_rows:
        connection.executemany(
            load_sql("insert_raw_lastfm_tag_snapshots.sql"),
            tag_rows,
        )
    if artist_rows:
        connection.executemany(
            load_sql("insert_raw_lastfm_artist_snapshots.sql"),
            artist_rows,
        )


def _append_checkpointed(
    database_path: Path,
    run_key: str,
    tag_snapshots: Sequence[LastfmTagSnapshot],
    artist_snapshots: Sequence[LastfmArtistSnapshot],
) -> None:
    tag_rows = _tag_rows(tag_snapshots)
    artist_rows = _artist_rows(artist_snapshots)
    completed_at = datetime.now(UTC)
    payload = json.dumps(
        {
            "artist_snapshots": len(artist_rows),
            "tag_snapshots": len(tag_rows),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            completed = connection.execute(
                load_sql("select_stg_collection_checkpoint.sql"),
                ["lastfm", run_key, "run", "completed"],
            ).fetchone()
            if completed is None:
                _insert_rows(connection, tag_rows, artist_rows)
                connection.execute(
                    load_sql("insert_stg_collection_checkpoint.sql"),
                    [
                        "lastfm",
                        run_key,
                        "run",
                        "completed",
                        None,
                        payload,
                        completed_at,
                    ],
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
