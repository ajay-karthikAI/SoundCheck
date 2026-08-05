"""Canonical genre mapping and persistence tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from soundcheck.ingest.lastfm.models import (
    LastfmArtistSnapshot,
    LastfmTagSnapshot,
)
from soundcheck.ingest.lastfm.storage import LastfmSnapshotWriter
from soundcheck.ingest.musicbrainz.models import (
    ArtistCreditRecord,
    RawMusicBrainzReleaseGroup,
    TagCountRecord,
)
from soundcheck.ingest.musicbrainz.storage import MusicBrainzReleaseGroupWriter
from soundcheck.resolve.genre_storage import DuckDBGenreResolutionStore
from soundcheck.resolve.genres import (
    CANONICAL_GENRE_MODEL,
    CanonicalGenreConfig,
    GenreResolutionBatch,
    SourceTag,
    load_canonical_genres,
    resolve_genres,
)
from soundcheck.sql.loader import load_sql

_NOW = datetime(2026, 7, 23, 12, tzinfo=UTC)


class FakeEmbedder:
    @property
    def model_name(self) -> str:
        return CANONICAL_GENRE_MODEL

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            if text in {"shoegaze", "ethereal wall music"}:
                vectors.append((1.0, 0.0))
            elif text == "ambient":
                vectors.append((0.0, 1.0))
            elif text == "space banjo":
                vectors.append((0.0, 0.0))
            else:
                vectors.append((-1.0, -1.0))
        return tuple(vectors)


class FakeGenreStore:
    def __init__(self) -> None:
        self.batch: GenreResolutionBatch | None = None

    async def initialize(self) -> None:
        return None

    async def load_source_tags(self) -> tuple[SourceTag, ...]:
        return (
            SourceTag(source_system="lastfm", raw_tag="dnb"),
            SourceTag(source_system="lastfm", raw_tag="shoegaze"),
            SourceTag(source_system="musicbrainz_tag", raw_tag="ethereal wall music"),
            SourceTag(source_system="musicbrainz_tag", raw_tag="space banjo"),
        )

    async def persist(self, batch: GenreResolutionBatch) -> tuple[int, int]:
        self.batch = batch
        return len(batch.mappings), len(batch.embeddings)


@pytest.mark.asyncio
async def test_overrides_exact_embedding_and_floor_are_distinct() -> None:
    config = load_canonical_genres()
    store = FakeGenreStore()

    counts = await resolve_genres(
        store,
        config,
        FakeEmbedder(),
        resolved_at=_NOW,
    )

    assert counts == (4, len(config.canonical_genres))
    assert store.batch is not None
    mappings = {mapping.raw_tag: mapping for mapping in store.batch.mappings}
    assert (mappings["dnb"].canonical_genre, mappings["dnb"].method) == (
        "drum and bass",
        "manual_override",
    )
    assert (mappings["shoegaze"].canonical_genre, mappings["shoegaze"].method) == (
        "shoegaze",
        "exact",
    )
    assert mappings["ethereal wall music"].canonical_genre == "shoegaze"
    assert mappings["ethereal wall music"].method == "embedding"
    assert mappings["space banjo"].canonical_genre == "other"
    assert mappings["space banjo"].method == "below_floor"
    assert all(
        len(embedding.embedding) == 2
        for embedding in store.batch.embeddings
    )


@pytest.mark.asyncio
async def test_duckdb_source_unification_and_idempotent_vector_persistence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "genres.duckdb"
    lastfm_writer = LastfmSnapshotWriter(database_path)
    await lastfm_writer.initialize()
    await lastfm_writer.append(
        (
            LastfmTagSnapshot(
                tag="shoegaze",
                reach=10,
                total=100,
                top_artists=(),
                top_albums=(),
                fetched_at=_NOW,
            ),
        ),
        (
            LastfmArtistSnapshot(
                artist_name="Artist",
                mbid=None,
                listeners=5,
                playcount=50,
                tags=("dnb",),
                source_genres=("shoegaze",),
                fetched_at=_NOW,
            ),
        ),
    )
    musicbrainz_writer = MusicBrainzReleaseGroupWriter(database_path)
    await musicbrainz_writer.initialize()
    await musicbrainz_writer.insert_first_sight(
        (
            RawMusicBrainzReleaseGroup(
                release_group_mbid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                title="Record",
                artist_credits=(
                    ArtistCreditRecord(
                        credit_name="Artist",
                        artist_name="Artist",
                        mbid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        join_phrase="",
                    ),
                ),
                artist_mbids=("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",),
                first_release_date="2026-07-20",
                types=("Album",),
                genres=("ambient",),
                tags=(TagCountRecord(name="space banjo", count=2),),
                fetched_at=_NOW,
            ),
        )
    )
    store = DuckDBGenreResolutionStore(database_path)
    config: CanonicalGenreConfig = load_canonical_genres()

    assert await resolve_genres(
        store,
        config,
        FakeEmbedder(),
        resolved_at=_NOW,
    ) == (4, len(config.canonical_genres))
    assert await resolve_genres(
        store,
        config,
        FakeEmbedder(),
        resolved_at=_NOW,
    ) == (4, len(config.canonical_genres))

    with duckdb.connect(str(database_path), read_only=True) as connection:
        summary = connection.execute(
            load_sql("summarize_stg_genre_resolution.sql")
        ).fetchone()
        mappings = connection.execute(
            load_sql("select_stg_tag_genre_map.sql")
        ).fetchall()
    assert summary == (4, len(config.canonical_genres))
    assert {row[1] for row in mappings} == {
        "ambient",
        "dnb",
        "shoegaze",
        "space banjo",
    }
