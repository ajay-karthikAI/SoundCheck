"""Fixture-DuckDB contracts for version-isolated forecast v2 artifacts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from soundcheck.forecast.storage import DuckDBForecastStore
from soundcheck.forecast.v2_pipeline import build_forecasts_v2
from soundcheck.forecast.v2_storage import DuckDBForecastV2Store
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import load_taxonomy


@pytest.mark.asyncio
async def test_v2_replace_preserves_v1_and_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "forecast-v2.duckdb"
    v1_store = DuckDBForecastStore(database_path)
    await v1_store.initialize()
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO fcst_.model_scores VALUES (
                'v1 sentinel', 'conversation', 1, 'naive',
                DATE '2026-01-05', DATE '2026-01-12',
                1, 0.1, 0.1, 1.0, 1.0, 0.2, 'scored',
                TIMESTAMPTZ '2026-07-27 00:00:00+00'
            )
            """
        )

    taxonomy = load_taxonomy()
    batch = build_forecasts_v2(
        (),
        taxonomy,
        created_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    store = DuckDBForecastV2Store(database_path)
    await store.initialize()
    expected = (
        len(batch.backtest_records),
        len(batch.model_scores),
        len(batch.predictions),
    )
    assert await store.replace(batch) == expected
    assert await store.replace(batch) == expected

    with duckdb.connect(str(database_path), read_only=True) as connection:
        v2_counts = connection.execute(
            load_sql("summarize_fcst_tables_v2.sql")
        ).fetchone()
        v1_count = connection.execute(
            "SELECT count(*) FROM fcst_.model_scores"
        ).fetchone()
    assert v2_counts == expected
    assert v1_count == (1,)


@pytest.mark.asyncio
async def test_v2_history_loader_pivots_context_metrics(tmp_path: Path) -> None:
    database_path = tmp_path / "history-v2.duckdb"
    store = DuckDBForecastV2Store(database_path)
    await store.initialize()
    week = date(2026, 7, 20)
    computed_at = datetime(2026, 7, 27, tzinfo=UTC)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            """
            INSERT INTO mart_.genre_weekly_v2 (
                taxonomy_version, week_start, iso_year, iso_week,
                genre_id, display_name, macro_family_id, parent_genre_id,
                coverage_state, estimate_status, estimate_eligible,
                conversation_effective_n, listening_effective_n,
                breakout_global, breakout_peer_family,
                conversation_post_uris, listening_artist_keys,
                supply_release_group_mbids, computed_at
            )
            VALUES (
                ?, ?, 2026, 30, 'genre_shoegaze', 'Shoegaze',
                'macro_rock', 'genre_alternative_rock',
                'ready', 'ready', true, 12.0, 15.0, false, false,
                [], [], [], ?
            )
            """,
            ["2.0.0", week, computed_at],
        )
        metric_rows = [
            (
                "global",
                "conversation",
                0.7,
                0.6,
                False,
            ),
            (
                "global",
                "listening",
                0.4,
                0.3,
                False,
            ),
            (
                "peer_family",
                "conversation",
                0.2,
                0.1,
                True,
            ),
            (
                "peer_family",
                "listening",
                -0.1,
                -0.2,
                False,
            ),
        ]
        connection.executemany(
            """
            INSERT INTO mart_.metric_estimates_v2 (
                taxonomy_version, week_start, scope_type, scope_id,
                macro_family_id, context, metric_name, estimate_status,
                estimate, ci_low, ci_high, ewma, ewma_ci_low, ewma_ci_high,
                spike, computed_at
            )
            VALUES (
                '2.0.0', ?, 'genre', 'genre_shoegaze', 'macro_rock',
                ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                (
                    week,
                    context,
                    metric_name,
                    estimate,
                    estimate - 0.1,
                    estimate + 0.1,
                    ewma,
                    ewma - 0.1,
                    ewma + 0.1,
                    spike,
                    computed_at,
                )
                for context, metric_name, estimate, ewma, spike in metric_rows
            ],
        )

    rows = await store.load_history("2.0.0")

    assert len(rows) == 2
    global_row = next(row for row in rows if row.context == "global")
    peer_row = next(row for row in rows if row.context == "peer_family")
    assert global_row.conversation == 0.7
    assert global_row.listening == 0.4
    assert peer_row.conversation == 0.2
    assert peer_row.conversation_spike is True
