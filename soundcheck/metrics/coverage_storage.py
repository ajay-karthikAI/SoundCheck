"""DuckDB persistence for the taxonomy-v2 source coverage layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from soundcheck.metrics.coverage import (
    BlueskyPostObservation,
    CoverageArtistCredit,
    CoverageBatch,
    CoverageEvidence,
    GenreCoverageRow,
    LastfmArtistObservation,
    LastfmTagObservation,
    MusicBrainzReleaseObservation,
    PostAmbiguityObservation,
    PostLinkObservation,
)
from soundcheck.sql.loader import load_sql


def initialize_coverage_storage(database_path: Path) -> None:
    """Create source and coverage tables without modifying existing evidence."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        for statement in (
            "create_raw_lastfm_snapshots.sql",
            "create_raw_mb_release_groups.sql",
            "create_raw_bluesky_posts.sql",
            "create_stg_post_artist_resolution.sql",
            "create_mart_genre_coverage_v2.sql",
        ):
            connection.execute(load_sql(statement))


def _credit(item: Any) -> CoverageArtistCredit:
    return CoverageArtistCredit(
        artist_name=str(item["artist_name"]),
        mbid=item.get("mbid"),
    )


def _tag_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item["name"])
    return str(item)


def load_coverage_evidence(database_path: Path) -> CoverageEvidence:
    """Load existing raw and staged evidence through validated models."""

    with duckdb.connect(str(database_path), read_only=True) as connection:
        tag_rows = connection.execute(
            load_sql("select_coverage_lastfm_tags.sql")
        ).fetchall()
        artist_rows = connection.execute(
            load_sql("select_coverage_lastfm_artists.sql")
        ).fetchall()
        release_rows = connection.execute(
            load_sql("select_coverage_musicbrainz_releases.sql")
        ).fetchall()
        post_rows = connection.execute(
            load_sql("select_coverage_bluesky_posts.sql")
        ).fetchall()
        link_rows = connection.execute(
            load_sql("select_coverage_post_links.sql")
        ).fetchall()
        ambiguity_rows = connection.execute(
            load_sql("select_coverage_post_ambiguities.sql")
        ).fetchall()

    return CoverageEvidence(
        lastfm_tags=tuple(
            LastfmTagObservation(tag=row[0], fetched_at=row[1]) for row in tag_rows
        ),
        lastfm_artists=tuple(
            LastfmArtistObservation(
                artist_name=row[0],
                mbid=row[1],
                listeners=row[2],
                playcount=row[3],
                tags=tuple(row[4] or ()),
                source_genres=tuple(row[5] or ()),
                fetched_at=row[6],
            )
            for row in artist_rows
        ),
        musicbrainz_releases=tuple(
            MusicBrainzReleaseObservation(
                release_group_mbid=row[0],
                first_release_date=row[1],
                artist_credits=tuple(_credit(item) for item in (row[2] or ())),
                genres=tuple(row[3] or ()),
                tags=tuple(_tag_name(item) for item in (row[4] or ())),
                fetched_at=row[5],
            )
            for row in release_rows
        ),
        bluesky_posts=tuple(
            BlueskyPostObservation(
                uri=row[0],
                created_at=row[1],
                ingested_at=row[2],
            )
            for row in post_rows
        ),
        post_links=tuple(
            PostLinkObservation(
                post_uri=row[0],
                artist_mbid=row[1],
                artist_name_raw=row[2],
                method=row[3],
                score=row[4],
                join_key_type=row[5],
                resolved_at=row[6],
            )
            for row in link_rows
        ),
        post_ambiguities=tuple(
            PostAmbiguityObservation(
                post_uri=row[0],
                top_artist_mbid=row[1],
                top_artist_name=row[2],
                resolved_at=row[3],
            )
            for row in ambiguity_rows
        ),
    )


def _row_values(row: GenreCoverageRow) -> tuple[object, ...]:
    return (
        row.taxonomy_version,
        row.week_start,
        row.iso_year,
        row.iso_week,
        row.genre_id,
        row.display_name,
        row.slug,
        row.macro_family_id,
        row.macro_family_name,
        row.taxonomy_status,
        row.lastfm_tag_available,
        row.unique_lastfm_artists,
        row.artists_with_consecutive_valid_snapshots,
        row.lastfm_history_weeks,
        row.musicbrainz_release_group_count,
        row.resolved_bluesky_post_count,
        row.resolution_attempt_count,
        row.resolution_rate,
        row.cross_source_overlap_artist_count,
        row.cross_source_overlap,
        row.latest_source_timestamp,
        row.listening_missing,
        row.conversation_missing,
        row.supply_missing,
        row.stale,
        row.eligibility_state,
        row.computed_at,
    )


def replace_coverage_batch(database_path: Path, batch: CoverageBatch) -> None:
    """Atomically replace one taxonomy version's computed coverage rows."""

    with duckdb.connect(str(database_path)) as connection:
        connection.begin()
        try:
            connection.execute(
                load_sql("delete_mart_genre_coverage_v2_version.sql"),
                [batch.taxonomy_version],
            )
            if batch.rows:
                connection.executemany(
                    load_sql("insert_mart_genre_coverage_v2.sql"),
                    [_row_values(row) for row in batch.rows],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def load_coverage_rows(
    database_path: Path,
    taxonomy_version: str,
) -> tuple[GenreCoverageRow, ...]:
    """Read persisted coverage rows for reporting."""

    with duckdb.connect(str(database_path), read_only=True) as connection:
        cursor = connection.execute(
            load_sql("select_mart_genre_coverage_v2.sql"),
            [taxonomy_version],
        )
        columns = tuple(item[0] for item in cursor.description)
        rows = cursor.fetchall()
    return tuple(
        GenreCoverageRow.model_validate(dict(zip(columns, row, strict=True)))
        for row in rows
    )
