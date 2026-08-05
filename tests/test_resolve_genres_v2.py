"""Taxonomy-v2 genre resolution and parallel persistence tests."""

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
from soundcheck.resolve.genre_storage_v2 import DuckDBGenreResolutionV2Store
from soundcheck.resolve.genres import (
    CANONICAL_GENRE_MODEL,
    GenreResolutionBatch,
    TagGenreMapping,
)
from soundcheck.resolve.genres_v2 import (
    ArtistTagEvidenceV2,
    GenreTagMappingV2,
    SourceTagV2,
    build_artist_memberships_v2,
    load_resolution_v2_config,
    resolve_genres_v2,
    resolve_source_tag_v2,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import load_taxonomy

_NOW = datetime(2026, 7, 26, 12, tzinfo=UTC)
_TAXONOMY_PATH = Path("tests/fixtures/taxonomy_v2.yml")


class FakeV2Embedder:
    @property
    def model_name(self) -> str:
        return CANONICAL_GENRE_MODEL

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            if text == "Garage Rock":
                vectors.append((0.9, 0.1))
            elif text == "Rock":
                vectors.append((1.0, 0.0))
            elif text == "UK Garage":
                vectors.append((0.0, 1.0))
            elif text == "rock adjacent":
                vectors.append((0.95, 0.05))
            elif text == "space banjo":
                vectors.append((0.0, 0.0))
            else:
                vectors.append((-1.0, -1.0))
        return tuple(vectors)


def _resolve(
    raw_tag: str,
    *,
    source: str = "lastfm",
) -> tuple[GenreTagMappingV2, ...]:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()
    embedder = FakeV2Embedder()
    canonical = tuple(
        genre
        for genre in taxonomy.genres
        if genre.status != "rejected"
        and genre.genre_id
        not in {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
    )
    vectors = embedder.encode(tuple(genre.display_name for genre in canonical))
    source_vectors = embedder.encode((raw_tag,))
    return resolve_source_tag_v2(
        SourceTagV2(source_system=source, source_tag=raw_tag),
        taxonomy,
        config,
        canonical_vectors={
            genre.genre_id: vector
            for genre, vector in zip(canonical, vectors, strict=True)
        },
        source_vector=source_vectors[0],
        model_name=embedder.model_name,
        resolved_at=_NOW,
    )


def test_precedence_multilingual_weighting_and_safe_fallbacks() -> None:
    manual = _resolve("garage")
    multilingual = _resolve("MÚSICA ROCK")
    embedded = _resolve("rock adjacent")
    below_floor = _resolve("space banjo")
    explicit_other = _resolve("other")
    explicit_unresolved = _resolve("unknown genre")

    assert [
        (item.canonical_genre_id, item.method)
        for item in manual
    ] == [("genre_garage_rock", "manual_override")]
    assert [
        (
            item.canonical_genre_id,
            item.method,
            item.language,
        )
        for item in multilingual
    ] == [("genre_rock", "exact_multilingual_alias", "es")]
    assert {item.canonical_genre_id for item in embedded} == {
        "genre_garage_rock",
        "genre_rock",
    }
    assert sum(item.membership_weight for item in embedded) == pytest.approx(1.0)
    assert below_floor[0].canonical_genre_id == "genre_unresolved"
    assert below_floor[0].method == "below_floor"
    assert (
        explicit_other[0].canonical_genre_id,
        explicit_unresolved[0].canonical_genre_id,
    ) == ("genre_other", "genre_unresolved")


def test_artist_can_have_weighted_macro_and_subgenre_memberships() -> None:
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()
    mappings = (
        *_resolve("rock", source="lastfm"),
        *_resolve("uk garage", source="musicbrainz_genre"),
        *_resolve("space banjo", source="musicbrainz_tag"),
    )
    artist_key = "mbid:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    evidence = tuple(
        ArtistTagEvidenceV2(
            artist_key_type="mbid",
            artist_key=artist_key,
            artist_mbid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            artist_name="Artist",
            source_system=source,
            source_tag=tag,
            evidence_at=_NOW,
        )
        for source, tag in (
            ("lastfm", "rock"),
            ("musicbrainz_genre", "uk garage"),
            ("musicbrainz_tag", "space banjo"),
        )
    )

    memberships, changed = build_artist_memberships_v2(
        evidence,
        mappings,
        config,
        resolved_at=_NOW,
        existing_states={},
        unresolved_genre_id=taxonomy.unresolved_genre_id,
    )

    assert changed.keys() == {artist_key}
    assert {item.canonical_genre_id for item in memberships} == {
        "genre_rock",
        "genre_uk_garage",
    }
    assert {item.macro_family_id for item in memberships} == {
        "macro_rock",
        "macro_electronic",
    }
    assert sum(item.membership_weight for item in memberships) == pytest.approx(1.0)
    by_genre = {item.canonical_genre_id: item for item in memberships}
    assert by_genre["genre_rock"].membership_weight == pytest.approx(3 / 7)
    assert by_genre["genre_uk_garage"].membership_weight == pytest.approx(4 / 7)


@pytest.mark.asyncio
async def test_parallel_tables_are_incremental_idempotent_and_preserve_v1(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "resolution-v2.duckdb"
    lastfm_writer = LastfmSnapshotWriter(database_path)
    await lastfm_writer.initialize()
    await lastfm_writer.append(
        (
            LastfmTagSnapshot(
                tag="rock adjacent",
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
                tags=("rock adjacent", "space banjo"),
                source_genres=("rock",),
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
                genres=("uk garage",),
                tags=(TagCountRecord(name="MÚSICA ROCK", count=2),),
                fetched_at=_NOW,
            ),
        )
    )
    v1_store = DuckDBGenreResolutionStore(database_path)
    await v1_store.initialize()
    await v1_store.persist(
        GenreResolutionBatch(
            mappings=(
                TagGenreMapping(
                    source_system="fixture",
                    raw_tag="v1 sentinel",
                    canonical_genre="rock",
                    similarity=1.0,
                    method="fixture",
                    model_name="fixture",
                    resolved_at=_NOW,
                ),
            ),
            embeddings=(),
        )
    )
    store = DuckDBGenreResolutionV2Store(database_path)
    taxonomy = load_taxonomy(_TAXONOMY_PATH)
    config = load_resolution_v2_config()

    first = await resolve_genres_v2(
        store,
        taxonomy,
        config,
        FakeV2Embedder(),
        resolved_at=_NOW,
    )
    second = await resolve_genres_v2(
        store,
        taxonomy,
        config,
        FakeV2Embedder(),
        resolved_at=_NOW,
    )

    assert first[0] >= 5
    assert first[1] == 3
    assert first[2] == 1
    assert second == (0, 0, 0)
    with duckdb.connect(str(database_path), read_only=True) as connection:
        v1_rows = connection.execute(
            load_sql("select_v1_genre_mapping_tags.sql")
        ).fetchall()
        membership_rows = connection.execute(
            load_sql("select_stg_artist_genre_memberships_v2.sql"),
            [taxonomy.taxonomy_version],
        ).fetchall()
        mapping_columns = {
            row[0]
            for row in connection.execute(
                load_sql("describe_stg_tag_genre_map_v2.sql")
            ).fetchall()
        }
    assert v1_rows == [("v1 sentinel",)]
    assert len(membership_rows) >= 2
    assert sum(float(row[4]) for row in membership_rows) == pytest.approx(1.0)
    assert {
        "source_tag",
        "canonical_genre_id",
        "macro_family_id",
        "parent_genre_id",
        "membership_weight",
        "method",
        "confidence",
        "taxonomy_version",
        "resolved_at",
    } <= mapping_columns
