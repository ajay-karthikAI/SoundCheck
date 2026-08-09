"""Public AppView engagement polling for 24-hour and 72-hour snapshots."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb
import httpx
from pydantic import BaseModel, ConfigDict

from soundcheck.ingest.bluesky.models import (
    AppViewGetPostsResponse,
    EngagementPollTask,
    EngagementSnapshot,
)
from soundcheck.ingest.bluesky.storage import EngagementWriter
from soundcheck.sql.loader import load_sql

APPVIEW_GET_POSTS_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
APPVIEW_BATCH_SIZE = 25


class AppViewSettings(BaseModel):
    """Validated CLI settings for one engagement poll."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    uris: tuple[str, ...] = ()
    due: bool = False
    overdue: bool = False
    limit: int = 500


class AppViewClient:
    """Async client for the unauthenticated public AppView endpoint."""

    def __init__(self, client: httpx.AsyncClient, max_attempts: int = 3) -> None:
        if max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)
        self._client = client
        self._max_attempts = max_attempts

    async def fetch_posts(self, uris: Sequence[str]) -> AppViewGetPostsResponse:
        """Fetch at most 25 post views, retrying transient HTTP failures."""
        if len(uris) > APPVIEW_BATCH_SIZE:
            msg = f"AppView accepts at most {APPVIEW_BATCH_SIZE} URIs per request"
            raise ValueError(msg)
        params = httpx.QueryParams([("uris", uri) for uri in uris])
        delay = 1.0
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(APPVIEW_GET_POSTS_URL, params=params)
                response.raise_for_status()
                return AppViewGetPostsResponse.model_validate_json(response.content)
            except (httpx.HTTPStatusError, httpx.TransportError):
                if attempt == self._max_attempts:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")


async def poll_engagement(
    uris: Sequence[str],
    client: AppViewClient,
    writer: EngagementWriter,
    *,
    fetched_at: datetime | None = None,
    poll_target_hours: Literal[24, 72] | None = None,
    poll_status: Literal["scheduled", "overdue_recovery", "ad_hoc"] = "ad_hoc",
) -> int:
    """Fetch and append one immutable poll for every accessible URI."""
    await writer.initialize()
    poll_time = fetched_at or datetime.now(UTC)
    written = 0
    for start in range(0, len(uris), APPVIEW_BATCH_SIZE):
        response = await client.fetch_posts(uris[start : start + APPVIEW_BATCH_SIZE])
        snapshots = [
            EngagementSnapshot(
                uri=post.uri,
                like_count=post.like_count,
                repost_count=post.repost_count,
                reply_count=post.reply_count,
                fetched_at=poll_time,
                poll_target_hours=poll_target_hours,
                poll_status=poll_status,
            )
            for post in response.posts
        ]
        written += await writer.append(snapshots)
    return written


async def poll_engagement_tasks(
    tasks: Sequence[EngagementPollTask],
    client: AppViewClient,
    writer: EngagementWriter,
    *,
    fetched_at: datetime | None = None,
) -> int:
    """Append every scheduled task, grouped by its maturity target."""

    written = 0
    groups: dict[
        tuple[
            Literal[24, 72],
            Literal["scheduled", "overdue_recovery"],
        ],
        list[str],
    ] = {}
    for task in tasks:
        groups.setdefault(
            (task.poll_target_hours, task.poll_status),
            [],
        ).append(task.uri)
    for (target_hours, poll_status), uris in sorted(groups.items()):
        written += await poll_engagement(
            uris,
            client,
            writer,
            fetched_at=fetched_at,
            poll_target_hours=target_hours,
            poll_status=poll_status,
        )
    return written


async def due_engagement_uris(
    database_path: Path,
    *,
    as_of: datetime | None = None,
) -> tuple[str, ...]:
    """Select posts missing their approximately 24h or 72h append-only poll."""
    poll_time = as_of or datetime.now(UTC)
    tasks = await eligible_engagement_tasks(
        database_path,
        as_of=poll_time,
    )
    return tuple(task.uri for task in tasks)


async def eligible_engagement_tasks(
    database_path: Path,
    *,
    as_of: datetime | None = None,
    overdue: bool = False,
    limit: int = 500,
) -> tuple[EngagementPollTask, ...]:
    """Select scheduled or overdue tasks; completed targets are restart-safe."""

    if limit <= 0:
        raise ValueError("limit must be positive")
    poll_time = as_of or datetime.now(UTC)
    return await asyncio.to_thread(
        _eligible_engagement_tasks,
        database_path,
        poll_time,
        overdue,
        limit,
    )


def _eligible_engagement_tasks(
    database_path: Path,
    as_of: datetime,
    overdue: bool,
    limit: int,
) -> tuple[EngagementPollTask, ...]:
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_raw_bluesky_posts.sql"))
        connection.execute(load_sql("create_raw_bluesky_engagement.sql"))
        statement = (
            "select_overdue_bluesky_engagement_tasks.sql"
            if overdue
            else "select_due_bluesky_engagement_uris.sql"
        )
        parameters: tuple[object, ...] = (
            (as_of, limit) if overdue else (as_of,)
        )
        rows = connection.execute(
            load_sql(statement),
            parameters,
        ).fetchall()
    return tuple(
        EngagementPollTask(
            uri=row[0],
            poll_target_hours=row[1],
            poll_status=row[2],
        )
        for row in rows
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uris", nargs="*", help="Specific AT URIs to poll")
    parser.add_argument(
        "--due",
        action="store_true",
        help="Poll posts missing their approximately 24h or 72h snapshot",
    )
    parser.add_argument(
        "--overdue",
        action="store_true",
        help="Resume overdue eligible 24h/72h polls in deterministic batches",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum overdue posts to recover per invocation (default: 500)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/soundcheck.duckdb"),
        help="DuckDB path (default: data/soundcheck.duckdb)",
    )
    return parser


async def async_main(settings: AppViewSettings) -> int:
    """Run one append-only engagement poll."""
    writer = EngagementWriter(settings.database_path)
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        client = AppViewClient(http_client)
        if settings.due or settings.overdue:
            tasks = await eligible_engagement_tasks(
                settings.database_path,
                overdue=settings.overdue,
                limit=settings.limit,
            )
            return await poll_engagement_tasks(tasks, client, writer)
        return await poll_engagement(settings.uris, client, writer)


def main() -> None:
    """CLI entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()
    if args.due and args.overdue:
        parser.error("--due and --overdue are mutually exclusive")
    if (args.due or args.overdue) and args.uris:
        parser.error("scheduled polling cannot be combined with explicit URIs")
    if not args.due and not args.overdue and not args.uris:
        parser.error("provide one or more URIs, --due, or --overdue")
    settings = AppViewSettings(
        database_path=args.database,
        uris=tuple(args.uris),
        due=args.due,
        overdue=args.overdue,
        limit=args.limit,
    )
    written = asyncio.run(async_main(settings))
    print(
        f'{{"event":"bluesky_engagement_complete","snapshots_appended":{written}}}'
    )


if __name__ == "__main__":
    main()
