"""Export the synthetic demo artifact into the frozen web API contract.

The generated JSON is a read-only deployment fallback for hosts that cannot
run the Python API. Every payload is produced by the real FastAPI application
from the isolated ``soundcheck-demo.duckdb`` artifact.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from soundcheck.api.app import create_app
from soundcheck.api.config import ApiSettings

DEFAULT_DATABASE_PATH = Path("data/soundcheck-demo.duckdb")
DEFAULT_OUTPUT_PATH = Path("soundcheck/web/data/demo-api.json")


def _read_json(
    client: TestClient,
    path: str,
    *,
    params: dict[str, str | int] | None = None,
) -> Any:
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def export_demo_web(database_path: Path, output_path: Path) -> None:
    """Write all frontend API payloads from the synthetic demo database."""
    app = create_app(ApiSettings(database_path=database_path))
    with TestClient(app) as client:
        health = _read_json(client, "/api/health")
        latest_week = date.fromisoformat(health["latest_metric_week"])
        weeks = [
            (latest_week - timedelta(weeks=index)).isoformat()
            for index in range(26)
        ]
        opportunities_by_week = {
            week: _read_json(
                client,
                "/api/genres/opportunities",
                params={"week": week, "limit": 100},
            )
            for week in weeks
        }
        latest_opportunities = opportunities_by_week[latest_week.isoformat()]
        genres = [row["genre"] for row in latest_opportunities]
        histories = {
            genre: _read_json(
                client,
                f"/api/genres/{genre}/timeseries",
                params={"weeks": 26},
            )
            for genre in genres
        }
        evidence = {
            genre: _read_json(
                client,
                f"/api/genres/{genre}/evidence",
                params={"week": latest_week.isoformat(), "limit": 20},
            )
            for genre in genres
        }
        payload = {
            "health": health,
            "opportunities_by_week": opportunities_by_week,
            "histories": histories,
            "evidence": evidence,
            "next_up": _read_json(
                client,
                "/api/forecast/next-up",
                params={"limit": 100},
            ),
            "ecosystem": _read_json(
                client,
                "/api/ecosystem",
                params={"weeks": 26},
            ),
            "briefs_by_week": {
                latest_week.isoformat(): _read_json(
                    client,
                    "/api/briefs",
                    params={"week": latest_week.isoformat()},
                )
            },
            "scene_map": _read_json(client, "/api/scene-map"),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    export_demo_web(args.database, args.output)


if __name__ == "__main__":
    main()
