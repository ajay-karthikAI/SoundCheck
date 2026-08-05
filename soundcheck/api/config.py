"""Validated API process settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from soundcheck.taxonomy import DEFAULT_TAXONOMY_PATH


class ApiSettings(BaseModel):
    """One worker's immutable read-only datastore and CORS settings."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    taxonomy_path: Path = DEFAULT_TAXONOMY_PATH
    production_origin: str | None = None
    cache_ttl_seconds: Literal[60] = 60

    @field_validator("production_origin")
    @classmethod
    def validate_production_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        origin = value.rstrip("/")
        if not origin.startswith(("http://", "https://")):
            msg = "production origin must be an absolute HTTP(S) origin"
            raise ValueError(msg)
        return origin

    @property
    def cors_origins(self) -> tuple[str, ...]:
        origins = ["http://localhost:3000"]
        if self.production_origin is not None:
            origins.append(self.production_origin)
        return tuple(origins)


def load_api_settings() -> ApiSettings:
    """Load the two deployment-specific values without another dependency."""
    return ApiSettings(
        database_path=Path(
            os.getenv("SOUNDCHECK_DB_PATH", "data/soundcheck.duckdb")
        ),
        taxonomy_path=Path(
            os.getenv("SOUNDCHECK_TAXONOMY_PATH", str(DEFAULT_TAXONOMY_PATH))
        ),
        production_origin=os.getenv("SOUNDCHECK_PROD_ORIGIN"),
    )
