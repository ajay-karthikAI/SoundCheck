"""Unify source folksonomies into a measured canonical genre space."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sentence_transformers import SentenceTransformer

from soundcheck.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    GenreTaxonomy,
    load_taxonomy,
)

CANONICAL_GENRE_MODEL = "all-MiniLM-L6-v2"
GENRE_COSINE_FLOOR = 0.55
DEFAULT_CANONICAL_GENRES_PATH = DEFAULT_TAXONOMY_PATH
type CanonicalGenreConfig = GenreTaxonomy


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "timestamp must include a timezone"
        raise ValueError(msg)
    return value.astimezone(UTC)


class SourceTag(BaseModel):
    """One distinct raw tag and its source system."""

    model_config = ConfigDict(frozen=True)

    source_system: str
    raw_tag: str


class TagGenreMapping(BaseModel):
    """Measured mapping from a source tag to a canonical genre."""

    model_config = ConfigDict(frozen=True)

    source_system: str
    raw_tag: str
    canonical_genre: str
    similarity: float = Field(ge=-1, le=1)
    method: str
    model_name: str
    resolved_at: datetime

    _resolved_at_utc = field_validator("resolved_at")(_as_utc)


class CanonicalGenreEmbedding(BaseModel):
    """Persisted canonical vector used by mapping and future scene maps."""

    model_config = ConfigDict(frozen=True)

    canonical_genre: str
    embedding: tuple[float, ...]
    model_name: str
    embedded_at: datetime

    _embedded_at_utc = field_validator("embedded_at")(_as_utc)


class GenreResolutionBatch(BaseModel):
    """Genre mappings and their exact canonical vector basis."""

    model_config = ConfigDict(frozen=True)

    mappings: tuple[TagGenreMapping, ...]
    embeddings: tuple[CanonicalGenreEmbedding, ...]


class GenreResolutionStore(Protocol):
    """DuckDB operations required for genre staging."""

    async def initialize(self) -> None:
        """Create genre staging tables."""
        ...

    async def load_source_tags(self) -> tuple[SourceTag, ...]:
        """Load distinct Last.fm and MusicBrainz tags."""
        ...

    async def persist(self, batch: GenreResolutionBatch) -> tuple[int, int]:
        """Upsert mappings and canonical vectors."""
        ...


class TextEmbedder(Protocol):
    """Embedding interface kept injectable for offline tests."""

    @property
    def model_name(self) -> str:
        """Stable model identifier."""
        ...

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Encode text into same-dimensional vectors."""
        ...


class SentenceTransformerEmbedder:
    """Production all-MiniLM-L6-v2 embedding adapter."""

    def __init__(self, model_name: str = CANONICAL_GENRE_MODEL) -> None:
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        values: Any = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return tuple(
            tuple(float(component) for component in vector)
            for vector in values
        )


def load_canonical_genres(
    path: Path = DEFAULT_CANONICAL_GENRES_PATH,
) -> CanonicalGenreConfig:
    """Load the shared taxonomy with its frozen Phase-B resolver view."""
    return load_taxonomy(path)


async def resolve_genres(
    store: GenreResolutionStore,
    config: CanonicalGenreConfig,
    embedder: TextEmbedder,
    *,
    resolved_at: datetime | None = None,
) -> tuple[int, int]:
    """Map all source tags and persist the exact vector basis."""
    await store.initialize()
    source_tags = await store.load_source_tags()
    resolution_time = resolved_at or datetime.now(UTC)
    canonical_vectors = await asyncio.to_thread(
        embedder.encode,
        config.canonical_genres,
    )
    if len(canonical_vectors) != len(config.canonical_genres):
        msg = "embedder returned the wrong number of canonical vectors"
        raise ValueError(msg)
    embeddings = tuple(
        CanonicalGenreEmbedding(
            canonical_genre=genre,
            embedding=vector,
            model_name=embedder.model_name,
            embedded_at=resolution_time,
        )
        for genre, vector in zip(
            config.canonical_genres,
            canonical_vectors,
            strict=True,
        )
    )
    vector_by_genre = {
        embedding.canonical_genre: embedding.embedding
        for embedding in embeddings
    }
    non_other_genres = tuple(
        genre for genre in config.canonical_genres if genre != "other"
    )
    unresolved = tuple(
        source_tag
        for source_tag in source_tags
        if source_tag.raw_tag.strip().casefold() not in config.manual_overrides
        and source_tag.raw_tag.strip().casefold() not in vector_by_genre
    )
    unresolved_vectors = await asyncio.to_thread(
        embedder.encode,
        tuple(source_tag.raw_tag for source_tag in unresolved),
    )
    if len(unresolved_vectors) != len(unresolved):
        msg = "embedder returned the wrong number of source-tag vectors"
        raise ValueError(msg)
    unresolved_lookup = {
        (source_tag.source_system, source_tag.raw_tag): vector
        for source_tag, vector in zip(unresolved, unresolved_vectors, strict=True)
    }

    mappings = tuple(
        _map_source_tag(
            source_tag,
            config.manual_overrides,
            vector_by_genre,
            non_other_genres,
            unresolved_lookup,
            embedder.model_name,
            resolution_time,
        )
        for source_tag in source_tags
    )
    return await store.persist(
        GenreResolutionBatch(mappings=mappings, embeddings=embeddings)
    )


def _map_source_tag(
    source_tag: SourceTag,
    overrides: Mapping[str, str],
    canonical_vectors: Mapping[str, tuple[float, ...]],
    non_other_genres: Sequence[str],
    unresolved_vectors: Mapping[tuple[str, str], tuple[float, ...]],
    model_name: str,
    resolved_at: datetime,
) -> TagGenreMapping:
    normalized = source_tag.raw_tag.strip().casefold()
    override = overrides.get(normalized)
    if override is not None:
        return TagGenreMapping(
            source_system=source_tag.source_system,
            raw_tag=source_tag.raw_tag,
            canonical_genre=override,
            similarity=1.0,
            method="manual_override",
            model_name=model_name,
            resolved_at=resolved_at,
        )
    if normalized in canonical_vectors:
        return TagGenreMapping(
            source_system=source_tag.source_system,
            raw_tag=source_tag.raw_tag,
            canonical_genre=normalized,
            similarity=1.0,
            method="exact",
            model_name=model_name,
            resolved_at=resolved_at,
        )

    source_vector = unresolved_vectors[
        (source_tag.source_system, source_tag.raw_tag)
    ]
    best_genre, best_similarity = max(
        (
            (
                genre,
                _cosine_similarity(source_vector, canonical_vectors[genre]),
            )
            for genre in non_other_genres
        ),
        key=lambda value: value[1],
    )
    accepted = best_similarity >= GENRE_COSINE_FLOOR
    return TagGenreMapping(
        source_system=source_tag.source_system,
        raw_tag=source_tag.raw_tag,
        canonical_genre=best_genre if accepted else "other",
        similarity=best_similarity,
        method="embedding" if accepted else "below_floor",
        model_name=model_name,
        resolved_at=resolved_at,
    )


def _cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right) or not left:
        msg = "cosine vectors must be non-empty and have equal dimensions"
        raise ValueError(msg)
    left_norm = math.sqrt(sum(component * component for component in left))
    right_norm = math.sqrt(sum(component * component for component in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
