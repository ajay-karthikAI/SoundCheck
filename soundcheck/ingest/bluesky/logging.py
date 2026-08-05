"""Compact JSON Lines logging with ingest counters."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class IngestCounters:
    """Observable Jetstream ingest counters."""

    seen: int = 0
    matched: int = 0
    written: int = 0


def log_event(
    logger: logging.Logger,
    event: str,
    counters: IngestCounters,
    **fields: Any,
) -> None:
    """Emit one JSON object suitable for line-oriented log collection."""
    payload: dict[str, Any] = {"event": event, **asdict(counters), **fields}
    logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def configure_logging(level: str) -> logging.Logger:
    """Configure message-only output so every emitted line remains valid JSON."""
    logging.basicConfig(level=level, format="%(message)s")
    return logging.getLogger("soundcheck.ingest.bluesky")

