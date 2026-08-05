"""Compatibility views over the shared taxonomy configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from soundcheck.taxonomy import (
    DEFAULT_TAXONOMY_PATH,
    SourceSystem,
    load_taxonomy,
)

DEFAULT_GENRES_PATH = DEFAULT_TAXONOMY_PATH


class GenreConfig(BaseModel):
    """The genre universe shared by listening and supply collection."""

    model_config = ConfigDict(frozen=True)

    genres: tuple[str, ...]

    @field_validator("genres")
    @classmethod
    def validate_genres(cls, genres: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(genre.strip() for genre in genres)
        if len(normalized) < 40:
            msg = "genre configuration must contain at least 40 tags"
            raise ValueError(msg)
        if any(not genre for genre in normalized):
            msg = "genre tags cannot be blank"
            raise ValueError(msg)
        if len({genre.casefold() for genre in normalized}) != len(normalized):
            msg = "genre tags must be unique, ignoring case"
            raise ValueError(msg)
        return normalized


def load_genres(
    path: Path = DEFAULT_GENRES_PATH,
    *,
    source: SourceSystem = "lastfm",
) -> GenreConfig:
    """Load enabled and candidate source tags from taxonomy v2."""
    return GenreConfig(genres=load_taxonomy(path).collection_tags_v2(source))
