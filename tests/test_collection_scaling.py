"""Fixture-only tests for scaled, resumable official-API collection."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pytest

from soundcheck.ingest.checkpoints import (
    CollectionCheckpointStore,
    CollectionRunMetadata,
)
from soundcheck.ingest.http import DiskJsonCache
from soundcheck.ingest.lastfm.client import LastfmClient
from soundcheck.ingest.lastfm.resumable import (
    artist_universe,
    collect_artist_shard,
    collect_tag_shard,
    finalize_lastfm_run,
    load_tag_discoveries,
)
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.ingest.musicbrainz.client import MusicBrainzClient
from soundcheck.ingest.musicbrainz.resumable import (
    collect_musicbrainz_shard,
    finalize_musicbrainz_run,
)
from soundcheck.ingest.musicbrainz.storage import MusicBrainzReleaseGroupWriter
from soundcheck.ingest.scaling import (
    ArtistCandidate,
    build_collection_plan,
    deduplicate_artist_candidates,
    deterministic_shard,
)
from soundcheck.sql.loader import load_sql

FIXTURES = Path(__file__).parent / "fixtures"


class NoopLimiter:
    async def acquire(self) -> None:
        return None


def _metadata(source: str, *, shard_count: int = 2) -> CollectionRunMetadata:
    return CollectionRunMetadata(
        taxonomy_version="2.0.0",
        shard_count=shard_count,
        snapshot_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        plan_fingerprint=(source[0] * 64),
    )


def test_global_artist_deduplication_and_deterministic_shards() -> None:
    artists = deduplicate_artist_candidates(
        (
            ArtistCandidate(
                name="Neon Hours",
                mbid=None,
                source_genre="shoegaze",
            ),
            ArtistCandidate(
                name="NEON HOURS",
                mbid="artist-neon",
                source_genre="dream pop",
            ),
            ArtistCandidate(
                name="Neon Hours",
                mbid="artist-neon",
                source_genre="indie rock",
            ),
        )
    )

    assert len(artists) == 1
    assert artists[0].request_key == "mbid:artist-neon"
    assert artists[0].source_genres == ("dream pop", "indie rock", "shoegaze")
    items = ("a", "b", "c", "d")
    first = deterministic_shard(items, shard_count=2, shard_index=0, key=str)
    second = deterministic_shard(items, shard_count=2, shard_index=1, key=str)
    assert set(first).isdisjoint(second)
    assert set(first) | set(second) == set(items)
    assert first == deterministic_shard(
        tuple(reversed(items)),
        shard_count=2,
        shard_index=0,
        key=str,
    )


def test_dry_run_plan_is_conservative_and_makes_no_network_calls(
    tmp_path: Path,
) -> None:
    plan = build_collection_plan(
        database_path=tmp_path / "absent.duckdb",
        taxonomy_path=FIXTURES / "taxonomy_v2.yml",
        config_path=FIXTURES / "collection_scaling.yml",
        as_of=date(2026, 7, 27),
        generated_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    assert plan.lastfm.tag_count == 3
    assert plan.lastfm.tag_requests == 9
    assert plan.lastfm.observed_deduplicated_artist_count == 0
    assert plan.lastfm.expected_deduplicated_artist_count == 30
    assert plan.lastfm.expected_requests_before_cache == 39
    assert plan.lastfm.requests_per_second == 4.0
    assert plan.musicbrainz.expected_pages == 4
    assert plan.musicbrainz.requests_per_second == 1.0
    assert plan.incremental_start_date == date(2026, 7, 13)
    assert plan.incremental_end_date == date(2026, 7, 26)


@pytest.mark.asyncio
async def test_lastfm_interrupted_shards_resume_and_append_once(
    tmp_path: Path,
    lastfm_responses: dict[str, Any],
) -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.params["method"]
        identity = request.url.params.get("tag", "")
        if method == "artist.getInfo":
            identity = request.url.params.get("mbid") or request.url.params["artist"]
            payload = lastfm_responses[method][identity]
        else:
            payload = lastfm_responses[method]
        requests.append((method, identity))
        return httpx.Response(200, json=payload)

    database = tmp_path / "lastfm-resume.duckdb"
    checkpoints = CollectionCheckpointStore(database)
    writer = LastfmSnapshotWriter(database)
    metadata = _metadata("lastfm")
    genres = ("dream pop", "shoegaze")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = LastfmClient(
            http_client,
            "fixture-key",
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "lastfm-cache", max_age_seconds=None),
        )
        await collect_tag_shard(
            genres,
            client,
            checkpoints,
            run_key="resume-lastfm",
            metadata=metadata,
            shard_index=0,
        )
        request_count_after_interruption = len(requests)
        assert (
            await collect_tag_shard(
                genres,
                client,
                checkpoints,
                run_key="resume-lastfm",
                metadata=metadata,
                shard_index=0,
            )
            == 0
        )
        assert len(requests) == request_count_after_interruption
        await collect_tag_shard(
            genres,
            client,
            checkpoints,
            run_key="resume-lastfm",
            metadata=metadata,
            shard_index=1,
        )
        discoveries = await load_tag_discoveries(
            genres,
            checkpoints,
            run_key="resume-lastfm",
        )
        assert len(artist_universe(discoveries)) == 2
        for shard_index in range(2):
            await collect_artist_shard(
                genres,
                client,
                checkpoints,
                run_key="resume-lastfm",
                metadata=metadata,
                shard_index=shard_index,
                concurrency=2,
            )
        assert await finalize_lastfm_run(
            genres,
            checkpoints,
            writer,
            run_key="resume-lastfm",
            metadata=metadata,
        ) == (2, 2)
        assert await finalize_lastfm_run(
            genres,
            checkpoints,
            writer,
            run_key="resume-lastfm",
            metadata=metadata,
        ) == (2, 2)

    artist_requests = [
        request for request in requests if request[0] == "artist.getInfo"
    ]
    assert len(artist_requests) == 2
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            load_sql("summarize_raw_lastfm_snapshots.sql")
        ).fetchone() == (2, 2, 1)


@pytest.mark.asyncio
async def test_musicbrainz_pagination_resumes_after_interruption(
    tmp_path: Path,
    musicbrainz_pages: dict[str, Any],
) -> None:
    offsets: list[str] = []
    failed_once = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal failed_once
        offset = request.url.params["offset"]
        offsets.append(offset)
        if offset == "1" and not failed_once:
            failed_once = True
            raise httpx.ConnectError("fixture interruption", request=request)
        return httpx.Response(200, json=musicbrainz_pages[offset])

    database = tmp_path / "musicbrainz-resume.duckdb"
    checkpoints = CollectionCheckpointStore(database)
    writer = MusicBrainzReleaseGroupWriter(database)
    metadata = _metadata("musicbrainz", shard_count=1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = MusicBrainzClient(
            http_client,
            limiter=NoopLimiter(),
            cache=DiskJsonCache(tmp_path / "mb-cache", max_age_seconds=None),
            max_attempts=1,
        )
        with pytest.raises(httpx.ConnectError):
            await collect_musicbrainz_shard(
                ("shoegaze",),
                date(2026, 7, 14),
                date(2026, 7, 27),
                client,
                writer,
                checkpoints,
                run_key="resume-mb",
                metadata=metadata,
                shard_index=0,
                max_tags_per_query=20,
            )
        assert offsets == ["0", "1"]
        assert await collect_musicbrainz_shard(
            ("shoegaze",),
            date(2026, 7, 14),
            date(2026, 7, 27),
            client,
            writer,
            checkpoints,
            run_key="resume-mb",
            metadata=metadata,
            shard_index=0,
            max_tags_per_query=20,
        ) == 2
        assert offsets == ["0", "1", "1"]
        assert await finalize_musicbrainz_run(
            checkpoints,
            run_key="resume-mb",
            metadata=metadata,
        ) == 2
        assert await collect_musicbrainz_shard(
            ("shoegaze",),
            date(2026, 7, 14),
            date(2026, 7, 27),
            client,
            writer,
            checkpoints,
            run_key="resume-mb",
            metadata=metadata,
            shard_index=0,
            max_tags_per_query=20,
        ) == 2
        assert offsets == ["0", "1", "1"]

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            load_sql("summarize_raw_mb_release_groups.sql")
        ).fetchone() == (2,)
