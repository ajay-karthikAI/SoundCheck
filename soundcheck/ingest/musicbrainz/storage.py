"""Insert-on-first-sight DuckDB storage for stable release groups."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import duckdb

from soundcheck.ingest.musicbrainz.models import RawMusicBrainzReleaseGroup
from soundcheck.sql.loader import load_sql


class MusicBrainzReleaseGroupWriter:
    """Persist the first observed representation of each release-group MBID."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        """Create the raw release-group table."""
        await asyncio.to_thread(_initialize, self._database_path)

    async def insert_first_sight(
        self,
        release_groups: Sequence[RawMusicBrainzReleaseGroup],
    ) -> int:
        """Attempt inserts without updating any previously observed MBID."""
        if not release_groups:
            return 0
        await asyncio.to_thread(
            _insert_release_groups,
            self._database_path,
            tuple(release_groups),
        )
        return len(release_groups)


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_raw_mb_release_groups.sql"))
        connection.execute(load_sql("create_stg_collection_checkpoints.sql"))


def _insert_release_groups(
    database_path: Path,
    release_groups: Sequence[RawMusicBrainzReleaseGroup],
) -> None:
    rows = [
        (
            release_group.release_group_mbid,
            release_group.title,
            [
                {
                    "credit_name": credit.credit_name,
                    "artist_name": credit.artist_name,
                    "mbid": credit.mbid,
                    "join_phrase": credit.join_phrase,
                }
                for credit in release_group.artist_credits
            ],
            list(release_group.artist_mbids),
            release_group.first_release_date,
            list(release_group.types),
            list(release_group.genres),
            [{"name": tag.name, "count": tag.count} for tag in release_group.tags],
            release_group.fetched_at,
        )
        for release_group in release_groups
    ]
    with duckdb.connect(str(database_path)) as connection:
        connection.executemany(load_sql("insert_raw_mb_release_groups.sql"), rows)
