"""One-connection, read-only DuckDB repository for FastAPI workers."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from soundcheck.api.models import (
    ArtistCredit,
    BacktestedModel,
    BlueskyEvidence,
    BlueskyFeedPost,
    CreatorBrief,
    EcosystemPoint,
    EffectiveSampleSizes,
    EstimateBand,
    GenreEvidenceResponse,
    GenreForecastPoint,
    GenreHistoryPoint,
    GenreTimeseriesResponse,
    HealthResponse,
    LastfmEvidence,
    MusicBrainzEvidence,
    NextUpRow,
    OpportunityRow,
    PipelineRowsIngested,
    PipelineRunHealth,
    SceneMapPoint,
    ShrinkageDiagnostics,
    SpikeFlags,
    TrendAxisPoint,
)
from soundcheck.api.v2_repository import DuckDBV2Repository
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import GenreTaxonomy

type QueryParameters = Sequence[object]


class DuckDBReadRepository:
    """Thin parameterized reads over precomputed mart_ and fcst_ artifacts."""

    def __init__(
        self,
        database_path: Path,
        *,
        cache_ttl_seconds: int,
        taxonomy: GenreTaxonomy,
    ) -> None:
        if not database_path.is_file():
            raise FileNotFoundError(database_path)
        self._connection = duckdb.connect(
            str(database_path),
            read_only=True,
        )
        self._lock = threading.Lock()
        self._cache_ttl_seconds = cache_ttl_seconds
        self.v2 = DuckDBV2Repository(
            self._connection,
            self._lock,
            taxonomy,
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def health(self) -> HealthResponse:
        row = self._one("api_health.sql")
        return HealthResponse(
            status="ok",
            datastore_mode="read_only",
            latest_metric_week=row[0],
            latest_forecast_week=row[1],
            latest_complete_week=row[2],
            metric_rows=row[3],
            forecast_rows=row[4],
            last_pipeline_run=_pipeline_run(row[5:]),
            cache_ttl_seconds=self._cache_ttl_seconds,
        )

    def latest_complete_week(self) -> date | None:
        return _date_or_none(self._one("api_latest_complete_week.sql")[0])

    def latest_metric_week(self) -> date | None:
        return _date_or_none(self._one("api_latest_metric_week.sql")[0])

    def latest_bluesky_feed_week(self) -> date | None:
        return _date_or_none(
            self._one("api_latest_bluesky_feed_week.sql")[0]
        )

    def canonical_genre(self, genre: str) -> str | None:
        rows = self._all("api_genre_exists.sql", (genre,))
        return None if not rows else rows[0][0]

    def opportunities(self, week: date, limit: int) -> tuple[OpportunityRow, ...]:
        return tuple(
            OpportunityRow(
                week=row[0],
                genre=row[1],
                opportunity=_band(row[2], row[3], row[4]),
                discovery_gap=_band(row[5], row[6], row[7]),
                z_conversation=_band(row[8], row[9], row[10]),
                z_listening=_band(row[11], row[12], row[13]),
                z_supply=_band(row[14], row[15], row[16]),
                shrinkage_weight=ShrinkageDiagnostics(
                    conversation=row[17],
                    supply=row[18],
                ),
                effective_n=EffectiveSampleSizes(
                    conversation=row[19],
                    supply=row[20],
                ),
                spike_flag=SpikeFlags(
                    conversation=row[21],
                    listening=row[22],
                    supply=row[23],
                ),
                breakout_flag=row[24],
            )
            for row in self._all("api_opportunities.sql", (week, limit))
        )

    def timeseries(self, genre: str, weeks: int) -> GenreTimeseriesResponse:
        history = tuple(
            _history_point(row)
            for row in self._all(
                "api_genre_timeseries.sql",
                (genre, weeks),
            )
        )
        forecasts = tuple(
            GenreForecastPoint(
                target_week=row[0],
                target_axis=row[1],
                horizon=row[2],
                model=row[3],
                skill_status=row[4],
                prediction_interval_80=_band(row[5], row[6], row[7]),
                backtest_mase=row[8],
                backtest_coverage_80=row[9],
                backtest_origins=row[10],
            )
            for row in self._all("api_genre_forecasts.sql", (genre,))
        )
        return GenreTimeseriesResponse(
            genre=genre,
            history=history,
            forecasts=forecasts,
        )

    def evidence(
        self,
        genre: str,
        week: date,
        limit: int,
    ) -> GenreEvidenceResponse:
        post_rows = self._all(
            "api_conversation_evidence.sql",
            (genre, week, limit),
        )
        artist_rows = self._all(
            "api_listening_evidence.sql",
            (genre, week, genre, week, limit),
        )
        release_rows = self._all(
            "api_supply_evidence.sql",
            (genre, week, limit),
        )
        return GenreEvidenceResponse(
            genre=genre,
            week=week,
            bluesky_posts=tuple(
                BlueskyEvidence(
                    uri=row[0],
                    did=row[1],
                    created_at=row[2],
                    text=row[3],
                    likes=row[4],
                    reposts=row[5],
                    replies=row[6],
                    artist_name_raw=row[7],
                    resolution_method=row[8],
                    resolution_score=row[9],
                    join_key_type=row[10],
                )
                for row in post_rows
            ),
            lastfm_artists=tuple(
                LastfmEvidence(
                    artist_key=row[0],
                    artist_name=row[1],
                    artist_mbid=row[2],
                    playcount_delta=row[3],
                    listeners_delta=row[4],
                    previous_fetched_at=row[5],
                    fetched_at=row[6],
                    interval_days=row[7],
                    listening_window_status=row[8],
                )
                for row in artist_rows
            ),
            musicbrainz_releases=tuple(
                MusicBrainzEvidence(
                    release_group_mbid=row[0],
                    title=row[1],
                    artist_credits=tuple(
                        ArtistCredit.model_validate(credit)
                        for credit in row[2]
                    ),
                    first_release_date=row[3],
                    types=tuple(row[4]),
                    genres=tuple(row[5]),
                )
                for row in release_rows
            ),
        )

    def bluesky_music_feed(
        self,
        week: date,
        limit: int,
    ) -> tuple[BlueskyFeedPost, ...]:
        return tuple(
            BlueskyFeedPost(
                uri=row[0],
                did=row[1],
                created_at=row[2],
                text=row[3],
                link_urls=tuple(row[4]),
                hashtags=tuple(row[5]),
                matched_rules=tuple(row[6]),
                likes=row[7],
                reposts=row[8],
                replies=row[9],
            )
            for row in self._all(
                "api_bluesky_music_feed.sql",
                (week, limit),
            )
        )

    def next_up(self, limit: int) -> tuple[NextUpRow, ...]:
        return tuple(
            NextUpRow(
                origin_week=row[0],
                target_week=row[1],
                genre=row[2],
                rank=row[3],
                predicted_opportunity=_band(row[4], row[5], row[6]),
                predicted_gain=_band(row[7], row[8], row[9]),
                conversation_model=BacktestedModel(
                    name=row[10],
                    mase=row[12],
                ),
                listening_model=BacktestedModel(
                    name=row[11],
                    mase=row[13],
                ),
                skill_status=row[14],
                breakout_evidence_week=row[15],
            )
            for row in self._all("api_next_up.sql", (limit,))
        )

    def ecosystem(self, weeks: int) -> tuple[EcosystemPoint, ...]:
        return tuple(
            EcosystemPoint(
                week=row[0],
                listening_entropy=_optional_band(row[1], row[2], row[3]),
                effective_genres=_optional_band(row[4], row[5], row[6]),
                conversation_hhi=_optional_band(row[7], row[8], row[9]),
                listening_top10_share=_optional_band(
                    row[10],
                    row[11],
                    row[12],
                ),
                scene_churn_jaccard_4w=_optional_band(
                    row[13],
                    row[14],
                    row[15],
                ),
                breakout_genres=tuple(row[16]),
                canonical_genre_count=row[17],
                listening_observed_genres=row[18],
                opportunity_observed_genres=row[19],
            )
            for row in self._all("api_ecosystem.sql", (weeks,))
        )

    def scene_map(self) -> tuple[SceneMapPoint, ...]:
        return tuple(
            SceneMapPoint(
                as_of_week=row[0],
                genre=row[1],
                x=row[2],
                y=row[3],
                opportunity=_optional_band(row[4], row[5], row[6]),
                discovery_gap=_optional_band(row[7], row[8], row[9]),
                evidence_volume=row[10],
            )
            for row in self._all("api_scene_map.sql")
        )

    def latest_brief_week(self) -> date | None:
        return _date_or_none(self._one("api_latest_brief_week.sql")[0])

    def briefs(self, week: date) -> tuple[CreatorBrief, ...]:
        return tuple(
            CreatorBrief(
                brief_id=row[0],
                week=row[1],
                genre=row[2],
                headline=row[3],
                opportunity=_band(row[4], row[5], row[6]),
                rationale=row[7],
                recommended_actions=tuple(row[8]),
                evidence_uris=tuple(row[9]),
                created_at=row[10],
            )
            for row in self._all("api_briefs.sql", (week,))
        )

    def _all(
        self,
        statement_name: str,
        parameters: QueryParameters = (),
    ) -> list[tuple[Any, ...]]:
        with self._lock:
            return self._connection.execute(
                load_sql(statement_name),
                parameters,
            ).fetchall()

    def _one(
        self,
        statement_name: str,
        parameters: QueryParameters = (),
    ) -> tuple[Any, ...]:
        rows = self._all(statement_name, parameters)
        if len(rows) != 1:
            msg = f"{statement_name} returned {len(rows)} rows; expected one"
            raise RuntimeError(msg)
        return rows[0]


def _history_point(row: tuple[Any, ...]) -> GenreHistoryPoint:
    return GenreHistoryPoint(
        week=row[0],
        conversation=TrendAxisPoint(
            index=_band(row[2], row[3], row[4]),
            ewma=_band(row[5], row[6], row[7]),
            spike=row[8],
        ),
        listening=_optional_trend_axis(
            row[9],
            row[10],
            row[11],
            row[12],
            row[13],
            row[14],
            row[15],
        ),
        supply=TrendAxisPoint(
            index=_band(row[16], row[17], row[18]),
            ewma=_band(row[19], row[20], row[21]),
            spike=row[22],
        ),
        opportunity=_optional_band(row[23], row[24], row[25]),
        discovery_gap=_optional_band(row[26], row[27], row[28]),
    )


def _optional_trend_axis(
    index: object,
    index_low: object,
    index_high: object,
    ewma: object,
    ewma_low: object,
    ewma_high: object,
    spike: object,
) -> TrendAxisPoint | None:
    if index is None:
        return None
    return TrendAxisPoint(
        index=_band(index, index_low, index_high),
        ewma=_band(ewma, ewma_low, ewma_high),
        spike=bool(spike),
    )


def _band(
    point: object,
    lower: object,
    upper: object,
) -> EstimateBand:
    return EstimateBand.model_validate(
        {
            "value": point,
            "lower": lower,
            "upper": upper,
        }
    )


def _optional_band(
    point: object,
    lower: object,
    upper: object,
) -> EstimateBand | None:
    if point is None:
        return None
    return _band(point, lower, upper)


def _date_or_none(value: object) -> date | None:
    if value is None or isinstance(value, date):
        return value
    msg = f"expected a date or null, received {type(value).__name__}"
    raise TypeError(msg)


def _pipeline_run(row: tuple[Any, ...]) -> PipelineRunHealth | None:
    if not row or row[0] is None:
        return None
    return PipelineRunHealth(
        run_id=row[0],
        run_kind=row[1],
        trigger=row[2],
        git_sha=row[3],
        status=row[4],
        started_at=row[5],
        completed_at=row[6],
        wall_time_seconds=row[7],
        rows_ingested=PipelineRowsIngested(
            bluesky_posts=row[8],
            bluesky_engagement_snapshots=row[9],
            lastfm_tag_snapshots=row[10],
            lastfm_artist_snapshots=row[11],
            musicbrainz_release_groups=row[12],
        ),
        resolution_posts_attempted=row[13],
        resolution_links_resolved=row[14],
        resolution_rate=row[15],
        metric_rows=row[16],
        forecast_rows=row[17],
        brief_rows=row[18],
        error_message=row[19],
    )
