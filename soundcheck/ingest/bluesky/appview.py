"""Public AppView engagement polling for 24-hour and 72-hour snapshots."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
from pydantic import BaseModel, ConfigDict

from soundcheck.ingest.bluesky.models import (
    AppViewGetPostsResponse,
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
            )
            for post in response.posts
        ]
        written += await writer.append(snapshots)
    return written


async def due_engagement_uris(
    database_path: Path,
    *,
    as_of: datetime | None = None,
) -> tuple[str, ...]:
    """Select posts missing their approximately 24h or 72h append-only poll."""
    poll_time = as_of or datetime.now(UTC)
    return await asyncio.to_thread(
        _due_engagement_uris,
        database_path,
        poll_time,
    )


def _due_engagement_uris(
    database_path: Path,
    as_of: datetime,
) -> tuple[str, ...]:
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_raw_bluesky_posts.sql"))
        connection.execute(load_sql("create_raw_bluesky_engagement.sql"))
        rows = connection.execute(
            load_sql("select_due_bluesky_engagement_uris.sql"),
            (as_of,),
        ).fetchall()
    return tuple(row[0] for row in rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uris", nargs="*", help="Specific AT URIs to poll")
    parser.add_argument(
        "--due",
        action="store_true",
        help="Poll posts missing their approximately 24h or 72h snapshot",
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
    uris = (
        await due_engagement_uris(settings.database_path)
        if settings.due
        else settings.uris
    )
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        client = AppViewClient(http_client)
        return await poll_engagement(uris, client, writer)


def main() -> None:
    """CLI entrypoint."""
    parser = _build_parser()
    args = parser.parse_args()
    if args.due and args.uris:
        parser.error("--due cannot be combined with explicit URIs")
    if not args.due and not args.uris:
        parser.error("provide one or more URIs or use --due")
    settings = AppViewSettings(
        database_path=args.database,
        uris=tuple(args.uris),
        due=args.due,
    )
    written = asyncio.run(async_main(settings))
    print(
        f'{{"event":"bluesky_engagement_complete","snapshots_appended":{written}}}'
    )


if __name__ == "__main__":
    main()
