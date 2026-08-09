"""Append-only DuckDB writers for the Bluesky raw schema."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from soundcheck.ingest.bluesky.models import EngagementSnapshot, RawBlueskyPost
from soundcheck.sql.loader import load_sql


class PostBatchWriter:
    """Buffer and append Bluesky posts in fixed-size batches."""

    def __init__(self, database_path: Path, batch_size: int = 100) -> None:
        if batch_size <= 0:
            msg = "batch_size must be positive"
            raise ValueError(msg)
        self._database_path = database_path
        self._batch_size = batch_size
        self._buffer: list[RawBlueskyPost] = []
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create the append-only table if it does not exist."""
        await asyncio.to_thread(
            _initialize_database,
            self._database_path,
            "create_raw_bluesky_posts.sql",
        )
        await asyncio.to_thread(
            _initialize_database,
            self._database_path,
            "create_raw_bluesky_cursors.sql",
        )

    async def latest_cursor(self) -> int | None:
        """Read the latest durable stream checkpoint."""
        return await asyncio.to_thread(
            _latest_cursor,
            self._database_path,
        )

    async def checkpoint_cursor(self, time_us: int) -> None:
        """Append the last completely processed Jetstream timestamp."""
        await asyncio.to_thread(
            _checkpoint_cursor,
            self._database_path,
            time_us,
        )

    async def add(self, post: RawBlueskyPost) -> int:
        """Buffer a post and return the number flushed by this call."""
        async with self._lock:
            self._buffer.append(post)
            if len(self._buffer) < self._batch_size:
                return 0
            return await self._flush_locked()

    async def flush(self) -> int:
        """Append all buffered posts, including a final partial batch."""
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        batch = tuple(self._buffer)
        await asyncio.to_thread(_insert_posts, self._database_path, batch)
        self._buffer.clear()
        return len(batch)


class EngagementWriter:
    """Append immutable AppView engagement snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        """Create the append-only table if it does not exist."""
        await asyncio.to_thread(
            _initialize_database,
            self._database_path,
            "create_raw_bluesky_engagement.sql",
        )

    async def append(self, snapshots: Sequence[EngagementSnapshot]) -> int:
        """Append a poll's snapshots and return the row count."""
        if not snapshots:
            return 0
        await asyncio.to_thread(_insert_engagement, self._database_path, tuple(snapshots))
        return len(snapshots)


def _initialize_database(database_path: Path, statement_name: str) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql(statement_name))


def _insert_posts(database_path: Path, posts: Sequence[RawBlueskyPost]) -> None:
    rows = [
        (
            post.uri,
            post.did,
            post.created_at,
            post.text,
            list(post.langs),
            list(post.link_urls),
            list(post.hashtags),
            list(post.matched_rules),
            post.ingested_at,
        )
        for post in posts
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.executemany(load_sql("insert_raw_bluesky_posts.sql"), rows)


def _insert_engagement(
    database_path: Path,
    snapshots: Sequence[EngagementSnapshot],
) -> None:
    rows = [
        (
            snapshot.uri,
            snapshot.like_count,
            snapshot.repost_count,
            snapshot.reply_count,
            snapshot.fetched_at,
            snapshot.poll_target_hours,
            snapshot.poll_status,
        )
        for snapshot in snapshots
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.executemany(
            load_sql("insert_raw_bluesky_engagement_poll.sql"),
            rows,
        )


def _latest_cursor(database_path: Path) -> int | None:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        row = connection.execute(
            load_sql("select_latest_raw_bluesky_cursor.sql")
        ).fetchone()
    return None if row is None else row[0]


def _checkpoint_cursor(database_path: Path, time_us: int) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            load_sql("insert_raw_bluesky_cursor.sql"),
            (time_us, datetime.now(UTC)),
        )
