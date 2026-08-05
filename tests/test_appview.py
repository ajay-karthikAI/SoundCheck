"""Offline public AppView polling tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest

from soundcheck.ingest.bluesky.appview import (
    AppViewClient,
    due_engagement_uris,
    poll_engagement,
)
from soundcheck.ingest.bluesky.models import (
    AppViewGetPostsResponse,
    EngagementSnapshot,
    RawBlueskyPost,
)
from soundcheck.ingest.bluesky.storage import EngagementWriter, PostBatchWriter
from soundcheck.sql.loader import load_sql


def test_appview_fixture_validation(appview_payload: dict[str, Any]) -> None:
    response = AppViewGetPostsResponse.model_validate(appview_payload)

    assert len(response.posts) == 2
    assert response.posts[0].like_count == 12
    assert response.posts[0].repost_count == 3
    assert response.posts[0].reply_count == 2


@pytest.mark.asyncio
async def test_appview_batches_25_and_appends_repolls(tmp_path: Path) -> None:
    requested_batch_sizes: list[int] = []

    def appview_handler(request: httpx.Request) -> httpx.Response:
        uris = request.url.params.get_list("uris")
        requested_batch_sizes.append(len(uris))
        return httpx.Response(
            200,
            json={
                "posts": [
                    {
                        "uri": uri,
                        "likeCount": index + 1,
                        "repostCount": index,
                        "replyCount": 0,
                    }
                    for index, uri in enumerate(uris)
                ]
            },
        )

    database_path = tmp_path / "engagement.duckdb"
    writer = EngagementWriter(database_path)
    transport = httpx.MockTransport(appview_handler)
    uris = tuple(
        f"at://did:plc:test/app.bsky.feed.post/{number}" for number in range(26)
    )
    first_poll = datetime(2026, 7, 21, 12, tzinfo=UTC)
    second_poll = datetime(2026, 7, 23, 12, tzinfo=UTC)

    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AppViewClient(http_client)
        assert await poll_engagement(
            uris,
            client,
            writer,
            fetched_at=first_poll,
        ) == 26
        assert await poll_engagement(
            uris,
            client,
            writer,
            fetched_at=second_poll,
        ) == 26

    assert requested_batch_sizes == [25, 1, 25, 1]
    with duckdb.connect(str(database_path), read_only=True) as connection:
        result = connection.execute(
            load_sql("summarize_raw_bluesky_engagement.sql")
        ).fetchone()
    assert result == (52, 2)


@pytest.mark.asyncio
async def test_due_polls_select_24h_and_72h_windows_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "due.duckdb"
    as_of = datetime(2026, 7, 24, 12, tzinfo=UTC)
    writer = PostBatchWriter(database_path, batch_size=10)
    await writer.initialize()
    posts = (
        RawBlueskyPost(
            uri=f"at://did:plc:test/app.bsky.feed.post/{age}",
            did="did:plc:test",
            created_at=as_of - timedelta(hours=age),
            text="Listening to Slowdive",
            langs=("en",),
            link_urls=(),
            hashtags=(),
            matched_rules=("intent:listening_to",),
            ingested_at=as_of - timedelta(hours=age),
        )
        for age in (24, 72, 48)
    )
    for post in posts:
        await writer.add(post)
    await writer.flush()
    engagement_writer = EngagementWriter(database_path)
    await engagement_writer.initialize()
    await engagement_writer.append(
        (
            EngagementSnapshot(
                uri="at://did:plc:test/app.bsky.feed.post/24",
                like_count=1,
                repost_count=0,
                reply_count=0,
                fetched_at=as_of,
            ),
        )
    )

    assert await due_engagement_uris(database_path, as_of=as_of) == (
        "at://did:plc:test/app.bsky.feed.post/72",
    )
