"""Soundcheck's cached, read-only FastAPI contract over mart_ and fcst_."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, Never

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from soundcheck.api.cache import TTLResponseCache
from soundcheck.api.config import ApiSettings, load_api_settings
from soundcheck.api.models import (
    ApiError,
    ApiErrorDetail,
    BlueskyFeedPost,
    CreatorBrief,
    EcosystemPoint,
    GenreEvidenceResponse,
    GenreTimeseriesResponse,
    HealthResponse,
    NextUpRow,
    OpportunityRow,
    SceneMapPoint,
)
from soundcheck.api.repository import DuckDBReadRepository
from soundcheck.api.v2_router import create_v2_router
from soundcheck.taxonomy import load_taxonomy

Limit = Annotated[int, Query(ge=1, le=200)]
Weeks = Annotated[int, Query(ge=1, le=260)]
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiError, "description": "Unknown canonical genre"},
    422: {"model": ApiError, "description": "Invalid request"},
}


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Create one API worker with one read-only DuckDB connection."""
    resolved_settings = settings or load_api_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        taxonomy = load_taxonomy(resolved_settings.taxonomy_path)
        repository = DuckDBReadRepository(
            resolved_settings.database_path,
            cache_ttl_seconds=resolved_settings.cache_ttl_seconds,
            taxonomy=taxonomy,
        )
        application.state.taxonomy = taxonomy
        application.state.repository = repository
        application.state.response_cache = TTLResponseCache(
            resolved_settings.cache_ttl_seconds
        )
        try:
            yield
        finally:
            repository.close()

    api = FastAPI(
        title="Soundcheck API",
        version="0.2.1",
        description=(
            "Read-only, uncertainty-bearing trend intelligence from "
            "precomputed mart_ and fcst_ artifacts."
        ),
        lifespan=lifespan,
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @api.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        envelope = ApiError(
            detail=ApiErrorDetail(
                code="validation_error",
                message=str(error),
            )
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(mode="json"),
        )

    @api.get(
        "/api/health",
        response_model=HealthResponse,
        summary="Check artifact recency and read-only datastore health",
    )
    def health(request: Request, response: Response) -> HealthResponse:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        cache = _cache(request)
        return cache.get_or_set(("health",), repository.health)

    @api.get(
        "/api/genres/opportunities",
        response_model=list[OpportunityRow],
        responses=ERROR_RESPONSES,
        summary="Rank attention-versus-supply opportunities",
    )
    def opportunities(
        request: Request,
        response: Response,
        week: date | None = None,
        limit: Limit = 50,
    ) -> tuple[OpportunityRow, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        selected_week = _selected_week(
            repository,
            week,
            latest="complete",
        )
        if selected_week is None:
            return ()
        cache = _cache(request)
        return cache.get_or_set(
            ("opportunities", selected_week, limit),
            lambda: repository.opportunities(selected_week, limit),
        )

    @api.get(
        "/api/evidence/bluesky",
        response_model=list[BlueskyFeedPost],
        responses=ERROR_RESPONSES,
        summary="Read publication-eligible public music conversation",
    )
    def bluesky_music_feed(
        request: Request,
        response: Response,
        week: date | None = None,
        limit: Limit = 50,
    ) -> tuple[BlueskyFeedPost, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        selected_week: date | None
        if week is not None:
            _validate_iso_week(week)
            selected_week = week
        else:
            selected_week = repository.latest_bluesky_feed_week()
        if selected_week is None:
            return ()
        return _cache(request).get_or_set(
            ("bluesky_music_feed", selected_week, limit),
            lambda: repository.bluesky_music_feed(
                selected_week,
                limit,
            ),
        )

    @api.get(
        "/api/genres/{genre}/timeseries",
        response_model=GenreTimeseriesResponse,
        responses=ERROR_RESPONSES,
        summary="Read historical axes and appended validated forecasts",
    )
    def genre_timeseries(
        genre: str,
        request: Request,
        response: Response,
        weeks: Weeks = 26,
    ) -> GenreTimeseriesResponse:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        canonical = _known_genre(repository, genre)
        cache = _cache(request)
        return cache.get_or_set(
            ("timeseries", canonical, weeks),
            lambda: repository.timeseries(canonical, weeks),
        )

    @api.get(
        "/api/genres/{genre}/evidence",
        response_model=GenreEvidenceResponse,
        responses=ERROR_RESPONSES,
        summary="Read raw receipts behind one genre-week",
    )
    def genre_evidence(
        genre: str,
        request: Request,
        response: Response,
        week: date | None = None,
        limit: Limit = 20,
    ) -> GenreEvidenceResponse:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        canonical = _known_genre(repository, genre)
        selected_week = _selected_week(
            repository,
            week,
            latest="metric",
        )
        if selected_week is None:
            return GenreEvidenceResponse(
                genre=canonical,
                week=_current_iso_week(),
                bluesky_posts=(),
                lastfm_artists=(),
                musicbrainz_releases=(),
            )
        cache = _cache(request)
        return cache.get_or_set(
            ("evidence", canonical, selected_week, limit),
            lambda: repository.evidence(canonical, selected_week, limit),
        )

    @api.get(
        "/api/forecast/next-up",
        response_model=list[NextUpRow],
        responses=ERROR_RESPONSES,
        summary="Rank breakout precursors by predicted opportunity gain",
    )
    def next_up(
        request: Request,
        response: Response,
        limit: Limit = 20,
    ) -> tuple[NextUpRow, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        return _cache(request).get_or_set(
            ("next_up", limit),
            lambda: repository.next_up(limit),
        )

    @api.get(
        "/api/ecosystem",
        response_model=list[EcosystemPoint],
        responses=ERROR_RESPONSES,
        summary="Read ecosystem diversity, concentration, and churn",
    )
    def ecosystem(
        request: Request,
        response: Response,
        weeks: Weeks = 26,
    ) -> tuple[EcosystemPoint, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        return _cache(request).get_or_set(
            ("ecosystem", weeks),
            lambda: repository.ecosystem(weeks),
        )

    @api.get(
        "/api/briefs",
        response_model=list[CreatorBrief],
        responses=ERROR_RESPONSES,
        summary="Read generated creator briefs once Phase 8 populates them",
    )
    def briefs(
        request: Request,
        response: Response,
        week: date | None = None,
    ) -> tuple[CreatorBrief, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        selected_week: date | None
        if week is not None:
            _validate_iso_week(week)
            selected_week = week
        else:
            selected_week = repository.latest_brief_week()
        if selected_week is None:
            return ()
        return _cache(request).get_or_set(
            ("briefs", selected_week),
            lambda: repository.briefs(selected_week),
        )

    @api.get(
        "/api/scene-map",
        response_model=list[SceneMapPoint],
        responses=ERROR_RESPONSES,
        summary="Read the latest batch-computed UMAP scene projection",
    )
    def scene_map(
        request: Request,
        response: Response,
    ) -> tuple[SceneMapPoint, ...]:
        _cache_headers(response, resolved_settings.cache_ttl_seconds)
        repository = _repository(request)
        return _cache(request).get_or_set(
            ("scene_map",),
            repository.scene_map,
        )

    api.include_router(
        create_v2_router(
            cache_ttl_seconds=resolved_settings.cache_ttl_seconds,
        )
    )

    return api


def _repository(request: Request) -> DuckDBReadRepository:
    value = request.app.state.repository
    if not isinstance(value, DuckDBReadRepository):
        raise RuntimeError("API repository is not initialized")
    return value


def _cache(request: Request) -> TTLResponseCache:
    value = request.app.state.response_cache
    if not isinstance(value, TTLResponseCache):
        raise RuntimeError("API response cache is not initialized")
    return value


def _known_genre(
    repository: DuckDBReadRepository,
    genre: str,
) -> str:
    canonical = repository.canonical_genre(genre)
    if canonical is None:
        _raise_api_error(
            404,
            "unknown_genre",
            f"Unknown canonical genre: {genre}",
        )
    return canonical


def _selected_week(
    repository: DuckDBReadRepository,
    week: date | None,
    *,
    latest: Literal["complete", "metric"],
) -> date | None:
    if week is not None:
        _validate_iso_week(week)
        return week
    if latest == "complete":
        return repository.latest_complete_week()
    return repository.latest_metric_week()


def _validate_iso_week(week: date) -> None:
    if week.weekday() != 0:
        _raise_api_error(
            422,
            "invalid_iso_week",
            "week must be the Monday starting an ISO week",
        )
    if week > _current_iso_week():
        _raise_api_error(
            422,
            "future_week",
            "future ISO weeks are not available",
        )


def _current_iso_week() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


def _raise_api_error(status_code: int, code: str, message: str) -> Never:
    raise HTTPException(
        status_code=status_code,
        detail=ApiErrorDetail(code=code, message=message).model_dump(
            mode="json"
        ),
    )


def _cache_headers(response: Response, ttl_seconds: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={ttl_seconds}"


app = create_app()
