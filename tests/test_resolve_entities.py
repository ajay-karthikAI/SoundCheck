"""Entity-resolution ladder and idempotency tests."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from pydantic import JsonValue, TypeAdapter

from soundcheck.ingest.bluesky.models import RawBlueskyPost
from soundcheck.ingest.bluesky.storage import PostBatchWriter
from soundcheck.ingest.http import QueryValue
from soundcheck.ingest.lastfm.models import LastfmArtistSnapshot
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.resolve.entities import (
    LastfmArtistCandidate,
    PostArtistLink,
    RawResolutionPost,
    ResolutionAttempt,
    ResolutionBatch,
    direct_lastfm_artist_name,
    direct_musicbrainz_mbid,
    extract_candidate_names,
    resolve_entities,
)
from soundcheck.resolve.entity_storage import DuckDBEntityResolutionStore
from soundcheck.sql.loader import load_sql

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
_NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


class FakeStore:
    def __init__(
        self,
        posts: tuple[RawResolutionPost, ...],
        artists: tuple[LastfmArtistCandidate, ...],
    ) -> None:
        self.posts = posts
        self.artists = artists
        self.batch: ResolutionBatch | None = None

    async def initialize(self) -> None:
        return None

    async def load_pending_posts(self) -> tuple[RawResolutionPost, ...]:
        return self.posts

    async def load_lastfm_artists(self) -> tuple[LastfmArtistCandidate, ...]:
        return self.artists

    async def persist(self, batch: ResolutionBatch) -> tuple[int, int, int]:
        self.batch = batch
        return len(batch.links), len(batch.ambiguities), len(batch.attempts)


class FakeMusicBrainzClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(
        self,
        method: str,
        params: Mapping[str, QueryValue],
    ) -> dict[str, JsonValue]:
        assert method == "artist"
        query = str(params["query"])
        self.calls.append(query)
        if "The Weeknd" in query:
            return _JSON_OBJECT.validate_python(
                {
                    "artists": [
                        {
                            "id": "11111111-1111-1111-1111-111111111111",
                            "name": "Abel Tesfaye",
                            "aliases": [{"name": "The Weeknd"}],
                        },
                        {
                            "id": "22222222-2222-2222-2222-222222222222",
                            "name": "Weekend",
                            "aliases": [],
                        },
                    ]
                }
            )
        if "Swell" in query:
            return _JSON_OBJECT.validate_python(
                {
                    "artists": [
                        {
                            "id": "33333333-3333-3333-3333-333333333333",
                            "name": "Swell",
                        },
                        {
                            "id": "44444444-4444-4444-4444-444444444444",
                            "name": "Swell Maps",
                        },
                    ]
                }
            )
        if "Beach House" in query or "U2" in query:
            return {"artists": []}
        return {"artists": []}


class FakeLastfmClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get(
        self,
        method: str,
        params: Mapping[str, QueryValue],
    ) -> dict[str, JsonValue]:
        assert method == "artist.getInfo"
        name = str(params["artist"])
        self.calls.append(name)
        return _JSON_OBJECT.validate_python(
            {
                "artist": {
                    "name": name,
                    "mbid": "55555555-5555-5555-5555-555555555555",
                    "stats": {"listeners": 10, "playcount": 100},
                    "tags": {"tag": []},
                }
            }
        )


def test_candidate_extraction_and_direct_url_guards() -> None:
    text = (
        '“Japanese Breakfast” and listening to My Bloody Valentine. '
        "A new Beach House album; Slowdive just dropped. 'M83' follows."
    )

    assert extract_candidate_names(text) == (
        "Japanese Breakfast",
        "My Bloody Valentine",
        "Beach House",
        "Slowdive",
        "M83",
    )
    assert direct_musicbrainz_mbid(
        "https://musicbrainz.org/artist/AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    ) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert direct_musicbrainz_mbid(
        "https://example.com/artist/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    ) is None
    assert (
        direct_lastfm_artist_name("https://www.last.fm/music/My+Bloody+Valentine")
        == "My Bloody Valentine"
    )


@pytest.mark.asyncio
async def test_ordered_ladder_alias_ambiguity_and_short_name_guard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    posts = (
        RawResolutionPost(
            uri="at://post/direct-mb",
            text="link",
            link_urls=(
                "https://musicbrainz.org/artist/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ),
        ),
        RawResolutionPost(
            uri="at://post/direct-lastfm",
            text="link",
            link_urls=("https://www.last.fm/music/Explicit+Artist",),
        ),
        RawResolutionPost(
            uri="at://post/search",
            text='Listening to "The Weeknd"',
            link_urls=(),
        ),
        RawResolutionPost(
            uri="at://post/ambiguous",
            text='Listening to "Swell"',
            link_urls=(),
        ),
        RawResolutionPost(
            uri="at://post/fallback",
            text="new Beach House album",
            link_urls=(),
        ),
        RawResolutionPost(
            uri="at://post/short",
            text="new U2 album",
            link_urls=(),
        ),
    )
    store = FakeStore(
        posts,
        (
            LastfmArtistCandidate(artist_name="Beach House", mbid=None),
            LastfmArtistCandidate(
                artist_name="U2",
                mbid="66666666-6666-6666-6666-666666666666",
            ),
        ),
    )
    musicbrainz = FakeMusicBrainzClient()
    lastfm = FakeLastfmClient()
    logger = logging.getLogger("test.resolve.entities")

    with caplog.at_level(logging.INFO, logger=logger.name):
        counts = await resolve_entities(
            store,
            musicbrainz,
            lastfm,
            logger=logger,
            resolved_at=_NOW,
        )

    assert counts == (4, 1, 6)
    assert store.batch is not None
    links = {link.post_uri: link for link in store.batch.links}
    assert links["at://post/direct-mb"].method == "direct_url"
    assert links["at://post/direct-mb"].join_key_type == "mbid"
    assert links["at://post/direct-lastfm"].artist_mbid == (
        "55555555-5555-5555-5555-555555555555"
    )
    assert links["at://post/search"].method == "musicbrainz_search"
    assert links["at://post/search"].score == 100
    assert links["at://post/fallback"].method == "lastfm_fuzzy"
    assert links["at://post/fallback"].join_key_type == "name"
    assert "at://post/short" not in links
    assert store.batch.ambiguities[0].artist_name_raw == "Swell"
    ambiguity_log = json.loads(caplog.records[-1].message)
    assert ambiguity_log["event"] == "ambiguous_artist"
    assert ambiguity_log["top_score"] - ambiguity_log["second_score"] <= 3


@pytest.mark.asyncio
async def test_duckdb_store_is_incremental_and_mbid_upgrades_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "resolution.duckdb"
    post_writer = PostBatchWriter(database_path, batch_size=1)
    await post_writer.initialize()
    await post_writer.add(
        RawBlueskyPost(
            uri="at://post/idempotent",
            did="did:plc:test",
            created_at=_NOW,
            text='Listening to "The Weeknd"',
            langs=("en",),
            link_urls=(),
            hashtags=(),
            matched_rules=("intent:listening_to",),
            ingested_at=_NOW,
        )
    )
    store = DuckDBEntityResolutionStore(database_path)
    musicbrainz = FakeMusicBrainzClient()
    lastfm = FakeLastfmClient()

    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW,
    ) == (1, 0, 1)
    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW,
    ) == (0, 0, 0)

    first_name_link = PostArtistLink(
        post_uri="at://post/upgrade",
        artist_mbid=None,
        artist_name_raw="Beach House",
        method="lastfm_fuzzy",
        score=100,
        join_key_type="name",
        resolved_at=_NOW,
    )
    mbid_link = first_name_link.model_copy(
        update={
            "artist_mbid": "77777777-7777-7777-7777-777777777777",
            "method": "musicbrainz_search",
            "score": 95,
            "join_key_type": "mbid",
        }
    )
    empty_attempt = ResolutionAttempt(
        post_uri="at://post/upgrade",
        outcome="resolved",
        candidate_count=1,
        attempted_at=_NOW,
    )
    await store.persist(
        ResolutionBatch(
            links=(first_name_link,),
            ambiguities=(),
            attempts=(empty_attempt,),
        )
    )
    await store.persist(
        ResolutionBatch(
            links=(mbid_link,),
            ambiguities=(),
            attempts=(empty_attempt,),
        )
    )

    with duckdb.connect(str(database_path), read_only=True) as connection:
        summary = connection.execute(
            load_sql("summarize_stg_entity_resolution.sql")
        ).fetchone()
        links = connection.execute(
            load_sql("select_stg_post_artist_links.sql")
        ).fetchall()
    assert summary == (2, 0, 2)
    upgraded = next(row for row in links if row[0] == "at://post/upgrade")
    assert upgraded[1] == "77777777-7777-7777-7777-777777777777"
    assert upgraded[5] == "mbid"


@pytest.mark.asyncio
async def test_unresolved_post_retries_only_after_new_upstream_snapshot(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "upstream-retry.duckdb"
    post_writer = PostBatchWriter(database_path, batch_size=1)
    await post_writer.initialize()
    await post_writer.add(
        RawBlueskyPost(
            uri="at://post/upstream-retry",
            did="did:plc:test",
            created_at=_NOW,
            text="new Beach House album",
            langs=("en",),
            link_urls=(),
            hashtags=(),
            matched_rules=("intent:new_album",),
            ingested_at=_NOW,
        )
    )
    store = DuckDBEntityResolutionStore(database_path)
    musicbrainz = FakeMusicBrainzClient()
    lastfm = FakeLastfmClient()

    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW,
    ) == (0, 0, 1)
    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW + timedelta(hours=1),
    ) == (0, 0, 0)

    lastfm_writer = LastfmSnapshotWriter(database_path)
    await lastfm_writer.initialize()
    await lastfm_writer.append(
        (),
        (
            LastfmArtistSnapshot(
                artist_name="Beach House",
                mbid="88888888-8888-8888-8888-888888888888",
                listeners=100,
                playcount=1000,
                tags=("dream pop",),
                source_genres=("dream pop",),
                fetched_at=_NOW + timedelta(days=1),
            ),
        ),
    )

    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW + timedelta(days=1),
    ) == (1, 0, 1)
    assert await resolve_entities(
        store,
        musicbrainz,
        lastfm,
        resolved_at=_NOW + timedelta(days=2),
    ) == (0, 0, 0)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        links = connection.execute(
            load_sql("select_stg_post_artist_links.sql")
        ).fetchall()
    assert links[0][1] == "88888888-8888-8888-8888-888888888888"
    assert links[0][5] == "mbid"
