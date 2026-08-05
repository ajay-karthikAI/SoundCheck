"""Run only taxonomy-v2 tag and artist-genre resolution."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from soundcheck.resolve.genre_storage_v2 import DuckDBGenreResolutionV2Store
from soundcheck.resolve.genres import SentenceTransformerEmbedder
from soundcheck.resolve.genres_v2 import (
    DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    load_resolution_v2_config,
    resolve_genres_v2,
)
from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH, load_taxonomy


class ResolveV2Settings(BaseModel):
    """Validated settings for the offline v2 resolution pass."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    resolution_config_path: Path = DEFAULT_RESOLUTION_V2_CONFIG_PATH


async def async_main(settings: ResolveV2Settings) -> dict[str, int | str]:
    """Resolve source tags and changed artists without source API calls."""
    taxonomy = load_taxonomy(settings.taxonomy_path)
    config = load_resolution_v2_config(settings.resolution_config_path)
    store = DuckDBGenreResolutionV2Store(settings.database_path)
    embedder = await asyncio.to_thread(SentenceTransformerEmbedder)
    mapping_count, embedding_count, artist_count = await resolve_genres_v2(
        store,
        taxonomy,
        config,
        embedder,
        resolved_at=datetime.now(UTC),
    )
    return {
        "event": "genre_resolution_v2_complete",
        "taxonomy_version": taxonomy.taxonomy_version,
        "tag_genre_mappings_written": mapping_count,
        "canonical_embeddings_written": embedding_count,
        "artists_changed": artist_count,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/soundcheck.duckdb"))
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY_PATH)
    parser.add_argument(
        "--resolution-config",
        type=Path,
        default=DEFAULT_RESOLUTION_V2_CONFIG_PATH,
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    settings = ResolveV2Settings(
        database_path=args.database,
        taxonomy_path=args.taxonomy,
        resolution_config_path=args.resolution_config,
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
