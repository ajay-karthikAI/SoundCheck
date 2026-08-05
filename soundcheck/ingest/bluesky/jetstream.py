"""Async public Bluesky Jetstream consumer for music conversation."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from soundcheck.ingest.bluesky.classify import is_music_post
from soundcheck.ingest.bluesky.logging import (
    IngestCounters,
    configure_logging,
    log_event,
)
from soundcheck.ingest.bluesky.models import FeedPost, JetstreamEvent, RawBlueskyPost
from soundcheck.ingest.bluesky.storage import PostBatchWriter

JETSTREAM_URL = (
    "wss://jetstream2.us-east.bsky.network/subscribe"
    "?wantedCollections=app.bsky.feed.post"
)


class JetstreamSettings(BaseModel):
    """Validated CLI settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    log_level: str = "INFO"
    duration_seconds: float | None = Field(default=None, gt=0)


class JetstreamIngestor:
    """Consume, classify, and batch-store public feed-post commits."""

    def __init__(
        self,
        writer: PostBatchWriter,
        logger: logging.Logger,
    ) -> None:
        self._writer = writer
        self._logger = logger
        self.counters = IngestCounters()
        self._last_time_us: int | None = None

    async def process_message(self, message: str | bytes) -> None:
        """Validate and process one Jetstream message."""
        self.counters.seen += 1
        try:
            event = JetstreamEvent.model_validate_json(message)
        except ValidationError as exc:
            log_event(
                self._logger,
                "invalid_event",
                self.counters,
                error_count=exc.error_count(),
            )
            return
        self._last_time_us = max(
            event.time_us,
            self._last_time_us or event.time_us,
        )

        commit = event.commit
        if (
            event.kind != "commit"
            or commit is None
            or commit.collection != "app.bsky.feed.post"
            or commit.record is None
            or commit.operation not in {"create", "update"}
        ):
            return

        try:
            post = FeedPost.model_validate(commit.record)
        except ValidationError as exc:
            log_event(
                self._logger,
                "invalid_post",
                self.counters,
                error_count=exc.error_count(),
            )
            return

        match = is_music_post(post)
        if not match:
            return

        self.counters.matched += 1
        raw_post = RawBlueskyPost(
            uri=f"at://{event.did}/app.bsky.feed.post/{commit.rkey}",
            did=event.did,
            created_at=post.created_at,
            text=post.text,
            langs=post.langs,
            link_urls=match.link_urls,
            hashtags=match.hashtags,
            matched_rules=match.rules,
            ingested_at=datetime.now(UTC),
        )
        written = await self._writer.add(raw_post)
        if written:
            await self._writer.checkpoint_cursor(self._last_time_us)
            self.counters.written += written
            log_event(self._logger, "batch_written", self.counters, batch_size=written)

    async def flush(self) -> int:
        """Flush a final partial batch and update counters."""
        written = await self._writer.flush()
        if self._last_time_us is not None:
            await self._writer.checkpoint_cursor(self._last_time_us)
        self.counters.written += written
        if written:
            log_event(self._logger, "final_batch_written", self.counters, batch_size=written)
        return written

    async def run(self, shutdown: asyncio.Event) -> None:
        """Run with reconnect backoff until shutdown is requested."""
        await self._writer.initialize()
        self._last_time_us = await self._writer.latest_cursor()
        log_event(
            self._logger,
            "started",
            self.counters,
            resume_cursor=self._last_time_us,
            url=_jetstream_url(self._last_time_us),
        )
        backoff_seconds = 1.0
        try:
            while not shutdown.is_set():
                try:
                    url = _jetstream_url(self._last_time_us)
                    async with connect(
                        url,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=2**20,
                    ) as websocket:
                        backoff_seconds = 1.0
                        await self._consume_connection(websocket, shutdown)
                except (ConnectionClosed, OSError) as exc:
                    if shutdown.is_set():
                        break
                    log_event(
                        self._logger,
                        "connection_error",
                        self.counters,
                        error=type(exc).__name__,
                        retry_seconds=backoff_seconds,
                    )
                    await _wait_or_shutdown(shutdown, backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 60.0)
        finally:
            await self.flush()
            log_event(self._logger, "stopped", self.counters)

    async def _consume_connection(
        self,
        websocket: ClientConnection,
        shutdown: asyncio.Event,
    ) -> None:
        while not shutdown.is_set():
            receive_task = asyncio.create_task(websocket.recv())
            shutdown_task = asyncio.create_task(shutdown.wait())
            done, pending = await asyncio.wait(
                {receive_task, shutdown_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError):
                    await task
            if shutdown_task in done:
                return
            message = receive_task.result()
            await self.process_message(message)


async def _wait_or_shutdown(shutdown: asyncio.Event, delay_seconds: float) -> None:
    with suppress(TimeoutError):
        async with asyncio.timeout(delay_seconds):
            await shutdown.wait()


def _jetstream_url(last_time_us: int | None) -> str:
    if last_time_us is None:
        return JETSTREAM_URL
    return f"{JETSTREAM_URL}&cursor={last_time_us + 1}"


async def _stop_after(shutdown: asyncio.Event, duration_seconds: float) -> None:
    await asyncio.sleep(duration_seconds)
    shutdown.set()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/soundcheck.duckdb"),
        help="DuckDB path (default: data/soundcheck.duckdb)",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="Stop and flush after this many seconds (default: run until a signal)",
    )
    return parser


def _install_signal_handlers(shutdown: asyncio.Event) -> Sequence[signal.Signals]:
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(handled_signal, shutdown.set)
            installed.append(handled_signal)
    return installed


async def async_main(settings: JetstreamSettings) -> None:
    """Run the configured consumer until SIGINT or SIGTERM."""
    shutdown = asyncio.Event()
    installed_signals = _install_signal_handlers(shutdown)
    logger = configure_logging(settings.log_level)
    writer = PostBatchWriter(settings.database_path, batch_size=100)
    ingestor = JetstreamIngestor(writer, logger)
    duration_task = (
        asyncio.create_task(_stop_after(shutdown, settings.duration_seconds))
        if settings.duration_seconds is not None
        else None
    )
    try:
        await ingestor.run(shutdown)
    finally:
        if duration_task is not None:
            duration_task.cancel()
            with suppress(asyncio.CancelledError):
                await duration_task
        loop = asyncio.get_running_loop()
        for handled_signal in installed_signals:
            loop.remove_signal_handler(handled_signal)


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    settings = JetstreamSettings(
        database_path=args.database,
        log_level=args.log_level,
        duration_seconds=args.duration_seconds,
    )
    asyncio.run(async_main(settings))


if __name__ == "__main__":
    main()
