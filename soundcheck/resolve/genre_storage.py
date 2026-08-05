"""DuckDB persistence for canonical genre mappings and vectors."""

from __future__ import annotations

import asyncio
from pathlib import Path

import duckdb

from soundcheck.resolve.genres import GenreResolutionBatch, SourceTag
from soundcheck.sql.loader import load_sql


class DuckDBGenreResolutionStore:
    """Load source tags and idempotently upsert mapping artifacts."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def load_source_tags(self) -> tuple[SourceTag, ...]:
        return await asyncio.to_thread(_load_source_tags, self._database_path)

    async def persist(self, batch: GenreResolutionBatch) -> tuple[int, int]:
        await asyncio.to_thread(_persist, self._database_path, batch)
        return len(batch.mappings), len(batch.embeddings)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_genre_resolution.sql"))


def _load_source_tags(database_path: Path) -> tuple[SourceTag, ...]:
    rows: list[tuple[str, str]] = []
    with duckdb.connect(str(database_path), read_only=True) as connection:
        for statement_name in (
            "select_lastfm_source_tags.sql",
            "select_musicbrainz_source_tags.sql",
        ):
            try:
                rows.extend(connection.execute(load_sql(statement_name)).fetchall())
            except duckdb.CatalogException:
                continue
    return tuple(
        SourceTag(source_system=source_system, raw_tag=raw_tag)
        for source_system, raw_tag in sorted(set(rows))
    )


def _persist(database_path: Path, batch: GenreResolutionBatch) -> None:
    mapping_rows = [
        (
            mapping.source_system,
            mapping.raw_tag,
            mapping.canonical_genre,
            mapping.similarity,
            mapping.method,
            mapping.model_name,
            mapping.resolved_at,
        )
        for mapping in batch.mappings
    ]
    embedding_rows = [
        (
            embedding.canonical_genre,
            list(embedding.embedding),
            embedding.model_name,
            embedding.embedded_at,
        )
        for embedding in batch.embeddings
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            if mapping_rows:
                connection.executemany(
                    load_sql("upsert_stg_tag_genre_map.sql"),
                    mapping_rows,
                )
            if embedding_rows:
                connection.executemany(
                    load_sql("upsert_stg_canonical_genre_embeddings.sql"),
                    embedding_rows,
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

