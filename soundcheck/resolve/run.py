"""Run incremental, idempotent entity and genre resolution."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from soundcheck.ingest.http import DiskJsonCache
from soundcheck.ingest.lastfm.client import LastfmClient
from soundcheck.ingest.musicbrainz.client import (
    MUSICBRAINZ_CACHE_MAX_AGE_SECONDS,
    MusicBrainzClient,
    musicbrainz_user_agent,
)
from soundcheck.resolve.entities import resolve_entities
from soundcheck.resolve.entity_storage import DuckDBEntityResolutionStore
from soundcheck.resolve.genre_storage import DuckDBGenreResolutionStore
from soundcheck.resolve.genre_storage_v2 import DuckDBGenreResolutionV2Store
from soundcheck.resolve.genres import (
    SentenceTransformerEmbedder,
    resolve_genres,
)
from soundcheck.resolve.genres_v2 import (
    DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    load_resolution_v2_config,
    resolve_genres_v2,
)
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy

DEFAULT_CANONICAL_GENRES_PATH = DEFAULT_TAXONOMY_PATH


class ResolveSettings(BaseModel):
    """Validated join-layer CLI settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    canonical_genres_path: Path = DEFAULT_CANONICAL_GENRES_PATH
    resolution_v2_config_path: Path = DEFAULT_RESOLUTION_V2_CONFIG_PATH
    lastfm_cache_directory: Path = Path(".cache/lastfm")
    musicbrainz_cache_directory: Path = Path(".cache/musicbrainz")


async def async_main(settings: ResolveSettings) -> dict[str, int | str]:
    """Run the entity ladder, then the canonical genre mapper."""
    run_time = datetime.now(UTC)
    entity_store = DuckDBEntityResolutionStore(settings.database_path)
    logger = logging.getLogger("soundcheck.resolve")
    musicbrainz_cache = DiskJsonCache(
        settings.musicbrainz_cache_directory,
        max_age_seconds=MUSICBRAINZ_CACHE_MAX_AGE_SECONDS,
    )
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        lastfm_client = LastfmClient.from_env(
            http_client,
            cache_directory=settings.lastfm_cache_directory,
        )
        musicbrainz_client = MusicBrainzClient(
            http_client,
            cache=musicbrainz_cache,
            user_agent=musicbrainz_user_agent(),
        )
        entity_counts = await resolve_entities(
            entity_store,
            musicbrainz_client,
            lastfm_client,
            logger=logger,
            resolved_at=run_time,
        )

    genre_store = DuckDBGenreResolutionStore(settings.database_path)
    genre_config = load_taxonomy(settings.canonical_genres_path)
    embedder = await asyncio.to_thread(SentenceTransformerEmbedder)
    genre_counts = await resolve_genres(
        genre_store,
        genre_config,
        embedder,
        resolved_at=run_time,
    )
    genre_v2_store = DuckDBGenreResolutionV2Store(settings.database_path)
    genre_v2_config = load_resolution_v2_config(
        settings.resolution_v2_config_path
    )
    genre_v2_counts = await resolve_genres_v2(
        genre_v2_store,
        genre_config,
        genre_v2_config,
        embedder,
        resolved_at=run_time,
    )
    return {
        "event": "resolution_complete",
        "artist_links": entity_counts[0],
        "artist_ambiguities": entity_counts[1],
        "posts_attempted": entity_counts[2],
        "tag_genre_mappings": genre_counts[0],
        "canonical_embeddings": genre_counts[1],
        "tag_genre_mappings_v2": genre_v2_counts[0],
        "canonical_embeddings_v2": genre_v2_counts[1],
        "artists_changed_v2": genre_v2_counts[2],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument(
        "--canonical-genres",
        type=Path,
        default=DEFAULT_CANONICAL_GENRES_PATH,
    )
    parser.add_argument(
        "--resolution-v2-config",
        type=Path,
        default=DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    )
    parser.add_argument("--lastfm-cache", type=Path, default=Path(".cache/lastfm"))
    parser.add_argument(
        "--musicbrainz-cache",
        type=Path,
        default=Path(".cache/musicbrainz"),
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args()
    settings = ResolveSettings(
        database_path=args.database,
        canonical_genres_path=args.canonical_genres,
        resolution_v2_config_path=args.resolution_v2_config,
        lastfm_cache_directory=args.lastfm_cache,
        musicbrainz_cache_directory=args.musicbrainz_cache,
    )
    print(
        json.dumps(
            asyncio.run(async_main(settings)),
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
