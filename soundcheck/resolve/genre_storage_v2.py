"""DuckDB storage for taxonomy-v2 tag mappings and artist memberships."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import duckdb

from soundcheck.resolve.genres_v2 import (
    ArtistGenreMembershipV2,
    ArtistResolutionStateV2,
    ArtistTagEvidenceV2,
    CanonicalGenreEmbeddingV2,
    GenreTagMappingV2,
    SourceTagV2,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import normalize_alias


class DuckDBGenreResolutionV2Store:
    """Preserve v1 tables while incrementally maintaining versioned v2 rows."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_unmapped_source_tags(
        self,
        taxonomy_version: str,
    ) -> tuple[SourceTagV2, ...]:
        return await asyncio.to_thread(
            _load_unmapped_source_tags,
            self._database_path,
            taxonomy_version,
        )

    async def load_tag_mappings(
        self,
        taxonomy_version: str,
    ) -> tuple[GenreTagMappingV2, ...]:
        return await asyncio.to_thread(
            _load_tag_mappings,
            self._database_path,
            taxonomy_version,
        )

    async def load_embedding_ids(
        self,
        taxonomy_version: str,
        model_name: str,
    ) -> frozenset[str]:
        return await asyncio.to_thread(
            _load_embedding_ids,
            self._database_path,
            taxonomy_version,
            model_name,
        )

    async def load_artist_evidence(self) -> tuple[ArtistTagEvidenceV2, ...]:
        return await asyncio.to_thread(_load_artist_evidence, self._database_path)

    async def load_artist_states(
        self,
        taxonomy_version: str,
    ) -> tuple[ArtistResolutionStateV2, ...]:
        return await asyncio.to_thread(
            _load_artist_states,
            self._database_path,
            taxonomy_version,
        )

    async def persist_tag_resolution(
        self,
        mappings: Sequence[GenreTagMappingV2],
        embeddings: Sequence[CanonicalGenreEmbeddingV2],
    ) -> tuple[int, int]:
        await asyncio.to_thread(
            _persist_tag_resolution,
            self._database_path,
            tuple(mappings),
            tuple(embeddings),
        )
        return len(mappings), len(embeddings)

    async def persist_artist_memberships(
        self,
        memberships: Sequence[ArtistGenreMembershipV2],
        changed_artist_fingerprints: Mapping[str, str],
        *,
        taxonomy_version: str,
        resolved_at: datetime,
    ) -> int:
        await asyncio.to_thread(
            _persist_artist_memberships,
            self._database_path,
            tuple(memberships),
            dict(changed_artist_fingerprints),
            taxonomy_version,
            resolved_at,
        )
        return len(changed_artist_fingerprints)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_genre_resolution_v2.sql"))


def _source_tags(database_path: Path) -> set[tuple[str, str]]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        try:
            return set(
                connection.execute(
                    load_sql("select_resolution_v2_source_tags.sql")
                ).fetchall()
            )
        except duckdb.CatalogException:
            return set()


def _load_unmapped_source_tags(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[SourceTagV2, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        existing = {
            (row[0], row[2])
            for row in connection.execute(
                load_sql("select_stg_tag_genre_map_v2.sql"),
                [taxonomy_version],
            ).fetchall()
        }
    return tuple(
        SourceTagV2(source_system=source, source_tag=tag)
        for source, tag in sorted(_source_tags(database_path))
        if (source, normalize_alias(tag)) not in existing
    )


def _load_tag_mappings(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[GenreTagMappingV2, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_stg_tag_genre_map_v2.sql"),
            [taxonomy_version],
        ).fetchall()
    return tuple(
        GenreTagMappingV2(
            source_system=row[0],
            source_tag=row[1],
            normalized_source_tag=row[2],
            canonical_genre_id=row[3],
            macro_family_id=row[4],
            parent_genre_id=row[5],
            membership_weight=row[6],
            method=row[7],
            confidence=row[8],
            language=row[9],
            model_name=row[10],
            taxonomy_version=row[11],
            resolved_at=row[12],
        )
        for row in rows
    )


def _load_embedding_ids(
    database_path: Path,
    taxonomy_version: str,
    model_name: str,
) -> frozenset[str]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_stg_canonical_genre_embedding_ids_v2.sql"),
            [taxonomy_version, model_name],
        ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def _load_artist_evidence(database_path: Path) -> tuple[ArtistTagEvidenceV2, ...]:
    raw_rows: list[tuple[object, ...]] = []
    with duckdb.connect(str(database_path), read_only=True) as connection:
        for statement in (
            "select_resolution_v2_lastfm_artist_tags.sql",
            "select_resolution_v2_musicbrainz_artist_tags.sql",
        ):
            try:
                raw_rows.extend(connection.execute(load_sql(statement)).fetchall())
            except duckdb.CatalogException:
                continue
    name_mbids: dict[str, set[str]] = defaultdict(set)
    for name, mbid, _source, _tag, _at in raw_rows:
        if mbid:
            name_mbids[normalize_alias(str(name))].add(str(mbid).casefold())
    unique_name_mbid = {
        name: next(iter(mbids))
        for name, mbids in name_mbids.items()
        if len(mbids) == 1
    }
    evidence = []
    for name, mbid, source, tag, evidence_at in raw_rows:
        normalized_name = normalize_alias(str(name))
        resolved_mbid = str(mbid).casefold() if mbid else unique_name_mbid.get(
            normalized_name
        )
        key_type = "mbid" if resolved_mbid else "name"
        artist_key = (
            f"mbid:{resolved_mbid}"
            if resolved_mbid
            else f"name:{normalized_name}"
        )
        evidence.append(
            ArtistTagEvidenceV2.model_validate(
                {
                    "artist_key_type": key_type,
                    "artist_key": artist_key,
                    "artist_mbid": resolved_mbid,
                    "artist_name": name,
                    "source_system": source,
                    "source_tag": tag,
                    "evidence_at": evidence_at,
                }
            )
        )
    return tuple(
        sorted(
            set(evidence),
            key=lambda item: (
                item.artist_key,
                item.source_system,
                normalize_alias(item.source_tag),
                item.evidence_at,
            ),
        )
    )


def _load_artist_states(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[ArtistResolutionStateV2, ...]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            load_sql("select_stg_artist_genre_states_v2.sql"),
            [taxonomy_version],
        ).fetchall()
    return tuple(
        ArtistResolutionStateV2(
            artist_key=row[0],
            input_fingerprint=row[1],
        )
        for row in rows
    )


def _persist_tag_resolution(
    database_path: Path,
    mappings: Sequence[GenreTagMappingV2],
    embeddings: Sequence[CanonicalGenreEmbeddingV2],
) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            if mappings:
                connection.executemany(
                    load_sql("insert_stg_tag_genre_map_v2.sql"),
                    [
                        (
                            item.source_system,
                            item.source_tag,
                            item.normalized_source_tag,
                            item.canonical_genre_id,
                            item.macro_family_id,
                            item.parent_genre_id,
                            item.membership_weight,
                            item.method,
                            item.confidence,
                            item.language,
                            item.model_name,
                            item.taxonomy_version,
                            item.resolved_at,
                        )
                        for item in mappings
                    ],
                )
            if embeddings:
                connection.executemany(
                    load_sql("upsert_stg_canonical_genre_embedding_v2.sql"),
                    [
                        (
                            item.canonical_genre_id,
                            item.macro_family_id,
                            item.parent_genre_id,
                            list(item.embedding),
                            item.model_name,
                            item.taxonomy_version,
                            item.embedded_at,
                        )
                        for item in embeddings
                    ],
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _persist_artist_memberships(
    database_path: Path,
    memberships: Sequence[ArtistGenreMembershipV2],
    changed: Mapping[str, str],
    taxonomy_version: str,
    resolved_at: datetime,
) -> None:
    by_artist: dict[str, list[ArtistGenreMembershipV2]] = defaultdict(list)
    for membership in memberships:
        by_artist[membership.artist_key].append(membership)
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            for artist_key, fingerprint in sorted(changed.items()):
                connection.execute(
                    load_sql("delete_stg_artist_genre_memberships_v2.sql"),
                    [taxonomy_version, artist_key],
                )
                artist_memberships = by_artist.get(artist_key, [])
                if artist_memberships:
                    connection.executemany(
                        load_sql("insert_stg_artist_genre_membership_v2.sql"),
                        [
                            (
                                item.artist_key_type,
                                item.artist_key,
                                item.artist_mbid,
                                item.artist_name,
                                item.canonical_genre_id,
                                item.macro_family_id,
                                item.parent_genre_id,
                                item.membership_weight,
                                item.method,
                                item.confidence,
                                list(item.source_systems),
                                list(item.source_tags),
                                item.input_fingerprint,
                                item.taxonomy_version,
                                item.resolved_at,
                            )
                            for item in artist_memberships
                        ],
                    )
                connection.execute(
                    load_sql("upsert_stg_artist_genre_state_v2.sql"),
                    [artist_key, fingerprint, taxonomy_version, resolved_at],
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
