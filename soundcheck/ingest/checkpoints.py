"""Immutable DuckDB checkpoints for resumable official-API collection."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from soundcheck.sql.loader import load_sql

CollectionSource = Literal["lastfm", "musicbrainz"]


class CollectionRunMetadata(BaseModel):
    """Immutable inputs that must match when a collection run resumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    shard_count: int = Field(ge=1)
    snapshot_at: datetime
    plan_fingerprint: str = Field(min_length=64, max_length=64)

    _snapshot_at_utc = field_validator("snapshot_at")(
        lambda value: value.astimezone(UTC)
    )


class CheckpointRecord(BaseModel):
    """One completed collection unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit_key: str
    shard_index: int | None
    payload_json: str
    completed_at: datetime

    _completed_at_utc = field_validator("completed_at")(
        lambda value: value.astimezone(UTC)
    )


class CollectionCheckpointStore:
    """Append immutable checkpoint units to DuckDB."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._database_path)

    async def ensure_run(
        self,
        source: CollectionSource,
        run_key: str,
        metadata: CollectionRunMetadata,
    ) -> None:
        """Create run metadata or verify an exact resume."""

        await self.initialize()
        payload = metadata.model_dump_json()
        await asyncio.to_thread(
            _insert_checkpoint,
            self._database_path,
            source,
            run_key,
            "run",
            "metadata",
            None,
            payload,
            datetime.now(UTC),
        )
        existing = await self.get(source, run_key, "run", "metadata")
        if existing is None or json.loads(existing.payload_json) != json.loads(payload):
            raise ValueError(
                "checkpoint metadata differs; use the original shard count and plan"
            )

    async def put(
        self,
        source: CollectionSource,
        run_key: str,
        phase: str,
        unit_key: str,
        *,
        shard_index: int | None,
        payload_json: str,
    ) -> None:
        """Record a completed unit idempotently and reject changed payloads."""

        completed_at = datetime.now(UTC)
        await asyncio.to_thread(
            _insert_checkpoint,
            self._database_path,
            source,
            run_key,
            phase,
            unit_key,
            shard_index,
            payload_json,
            completed_at,
        )
        existing = await self.get(source, run_key, phase, unit_key)
        if existing is None or json.loads(existing.payload_json) != json.loads(
            payload_json
        ):
            raise ValueError("checkpoint unit already exists with different evidence")

    async def get(
        self,
        source: CollectionSource,
        run_key: str,
        phase: str,
        unit_key: str,
    ) -> CheckpointRecord | None:
        row = await asyncio.to_thread(
            _get_checkpoint,
            self._database_path,
            source,
            run_key,
            phase,
            unit_key,
        )
        if row is None:
            return None
        return CheckpointRecord.model_validate(
            {
                "unit_key": unit_key,
                "shard_index": row[0],
                "payload_json": row[1],
                "completed_at": row[2],
            }
        )

    async def phase(
        self,
        source: CollectionSource,
        run_key: str,
        phase: str,
    ) -> tuple[CheckpointRecord, ...]:
        rows = await asyncio.to_thread(
            _get_phase,
            self._database_path,
            source,
            run_key,
            phase,
        )
        return tuple(
            CheckpointRecord.model_validate(
                {
                    "unit_key": row[0],
                    "shard_index": row[1],
                    "payload_json": row[2],
                    "completed_at": row[3],
                }
            )
            for row in rows
        )

    async def mark_completed(
        self,
        source: CollectionSource,
        run_key: str,
        *,
        payload_json: str,
    ) -> None:
        await self.put(
            source,
            run_key,
            "run",
            "completed",
            shard_index=None,
            payload_json=payload_json,
        )

    async def is_completed(self, source: CollectionSource, run_key: str) -> bool:
        return await self.get(source, run_key, "run", "completed") is not None


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(load_sql("create_stg_collection_checkpoints.sql"))


def _insert_checkpoint(
    database_path: Path,
    source: CollectionSource,
    run_key: str,
    phase: str,
    unit_key: str,
    shard_index: int | None,
    payload_json: str,
    completed_at: datetime,
) -> None:
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            load_sql("insert_stg_collection_checkpoint.sql"),
            [
                source,
                run_key,
                phase,
                unit_key,
                shard_index,
                payload_json,
                completed_at,
            ],
        )


def _get_checkpoint(
    database_path: Path,
    source: CollectionSource,
    run_key: str,
    phase: str,
    unit_key: str,
) -> tuple[object, ...] | None:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        return connection.execute(
            load_sql("select_stg_collection_checkpoint.sql"),
            [source, run_key, phase, unit_key],
        ).fetchone()


def _get_phase(
    database_path: Path,
    source: CollectionSource,
    run_key: str,
    phase: str,
) -> list[tuple[object, ...]]:
    with duckdb.connect(str(database_path), read_only=True) as connection:
        return connection.execute(
            load_sql("select_stg_collection_checkpoint_phase.sql"),
            [source, run_key, phase],
        ).fetchall()
