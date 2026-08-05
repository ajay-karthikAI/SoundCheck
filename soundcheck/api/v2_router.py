"""Non-breaking `/api/v2` routes over precomputed taxonomy-v2 artifacts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Never

from fastapi import APIRouter, HTTPException, Query, Request, Response

from soundcheck.api.cache import TTLResponseCache
from soundcheck.api.models import ApiError, ApiErrorDetail
from soundcheck.api.repository import DuckDBReadRepository
from soundcheck.api.v2_models import (
    ComparisonContextV2,
    CoveragePageV2,
    CoverageStatusV2,
    CreatorBriefPageV2,
    CursorPageMeta,
    EcosystemPointV2,
    EvidencePageV2,
    EvidenceSourceV2,
    ForecastPageV2,
    GenreCatalogPageV2,
    GenreIdentityV2,
    GenreTimeseriesResponseV2,
    MacroFamilyPageV2,
    MacroFamilyV2,
    NextUpPageV2,
    OpportunityPageV2,
    SceneMapPageV2,
    TaxonomyResponseV2,
)
from soundcheck.api.v2_pagination import decode_cursor, encode_cursor
from soundcheck.api.v2_repository import DuckDBV2Repository
from soundcheck.taxonomy import GenreTaxonomy, normalize_alias

V2Limit = Annotated[int, Query(ge=1, le=200)]
V2Weeks = Annotated[int, Query(ge=1, le=260)]
SearchText = Annotated[str, Query(min_length=1, max_length=100)]
V2_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiError, "description": "Unknown stable identifier"},
    422: {"model": ApiError, "description": "Invalid v2 request"},
}


def create_v2_router(*, cache_ttl_seconds: int) -> APIRouter:
    """Build the independently versioned router without changing v1 routes."""
    router = APIRouter(prefix="/api/v2", tags=["API v2"])

    @router.get(
        "/taxonomy",
        response_model=TaxonomyResponseV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read the versioned hierarchical genre taxonomy",
    )
    def taxonomy(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = None,
        limit: V2Limit = 100,
        cursor: str | None = None,
    ) -> TaxonomyResponseV2:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        _validate_filter_ids(catalog, macro_family_id, parent_genre_id)
        offset = _offset(cursor)
        statuses = _v2(request).coverage_statuses(version)
        items = _catalog(
            catalog,
            statuses,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
        )
        visible, page = _slice_page(items, offset, limit)
        return TaxonomyResponseV2(
            taxonomy_version=version,
            default_genre_id=catalog.default_genre_id,
            other_genre_id=catalog.other_genre_id,
            unresolved_genre_id=catalog.unresolved_genre_id,
            genres=GenreCatalogPageV2(items=visible, page=page),
        )

    @router.get(
        "/macro-families",
        response_model=MacroFamilyPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read stable taxonomy macro families",
    )
    def macro_families(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        limit: V2Limit = 100,
        cursor: str | None = None,
    ) -> MacroFamilyPageV2:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        families = tuple(
            MacroFamilyV2(
                macro_family_id=family.macro_family_id,
                display_name=family.display_name,
                slug=family.slug,
            )
            for family in catalog.macro_families
        )
        visible, page = _slice_page(families, _offset(cursor), limit)
        return MacroFamilyPageV2(
            taxonomy_version=version,
            items=visible,
            page=page,
        )

    @router.get(
        "/genres/search",
        response_model=GenreCatalogPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Search stable genre names, slugs, and aliases",
    )
    def genre_search(
        request: Request,
        response: Response,
        q: SearchText,
        taxonomy_version: str | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = None,
        limit: V2Limit = 50,
        cursor: str | None = None,
    ) -> GenreCatalogPageV2:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        _validate_filter_ids(catalog, macro_family_id, parent_genre_id)
        statuses = _v2(request).coverage_statuses(version)
        items = _catalog(
            catalog,
            statuses,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            query=q,
        )
        visible, page = _slice_page(items, _offset(cursor), limit)
        return GenreCatalogPageV2(items=visible, page=page)

    @router.get(
        "/opportunities",
        response_model=OpportunityPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Rank global or peer-family attention versus supply",
    )
    def opportunities(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        week: date | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = "ready",
        context: ComparisonContextV2 = "global",
        limit: V2Limit = 50,
        cursor: str | None = None,
    ) -> OpportunityPageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog_value, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        selected_week = _selected_week(
            week,
            _v2(request).latest_opportunity_week(version, context),
        )
        offset = _offset(cursor)
        if selected_week is None:
            return OpportunityPageV2(
                taxonomy_version=version,
                week=None,
                context=context,
                items=(),
                page=CursorPageMeta(next_cursor=None, has_more=False),
            )
        items = _v2(request).opportunities(
            taxonomy_version=version,
            week=selected_week,
            context=context,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return OpportunityPageV2(
            taxonomy_version=version,
            week=selected_week,
            context=context,
            items=visible,
            page=page,
        )

    @router.get(
        "/genres/{genre_id}/timeseries",
        response_model=GenreTimeseriesResponseV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read v2 metric history and validated forecast statuses",
    )
    def timeseries(
        genre_id: str,
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        context: ComparisonContextV2 = "global",
        weeks: V2Weeks = 26,
    ) -> GenreTimeseriesResponseV2:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        _known_genre(catalog, genre_id)
        repository = _v2(request)
        status = repository.coverage_statuses(version).get(
            genre_id,
            "not_observed",
        )
        forecasts = repository.forecasts(
            taxonomy_version=version,
            context=context,
            macro_family_id=None,
            parent_genre_id=None,
            eligibility_state=None,
            genre_id=genre_id,
            limit=1_000,
            offset=0,
        )
        return GenreTimeseriesResponseV2(
            genre=repository.identity(genre_id, status),
            context=context,
            history=repository.genre_history(
                taxonomy_version=version,
                genre_id=genre_id,
                context=context,
                weeks=weeks,
            ),
            forecasts=forecasts,
        )

    @router.get(
        "/genres/{genre_id}/evidence",
        response_model=EvidencePageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read direct materialized source receipts for one genre-week",
    )
    def evidence(
        genre_id: str,
        request: Request,
        response: Response,
        source: EvidenceSourceV2,
        taxonomy_version: str | None = None,
        week: date | None = None,
        limit: V2Limit = 20,
        cursor: str | None = None,
    ) -> EvidencePageV2:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        _known_genre(catalog, genre_id)
        repository = _v2(request)
        selected_week = _selected_week(
            week,
            repository.latest_coverage_week(version),
        )
        if selected_week is None:
            selected_week = _current_iso_week()
        offset = _offset(cursor)
        items = repository.evidence(
            taxonomy_version=version,
            genre_id=genre_id,
            week=selected_week,
            source=source,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        status = repository.coverage_statuses(version, selected_week).get(
            genre_id,
            "not_observed",
        )
        return EvidencePageV2(
            genre=repository.identity(genre_id, status),
            week=selected_week,
            source=source,
            items=visible,
            page=page,
        )

    @router.get(
        "/forecasts",
        response_model=ForecastPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read current v2 forecasts, cold starts, and naive baselines",
    )
    def forecasts(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = None,
        context: ComparisonContextV2 = "global",
        limit: V2Limit = 50,
        cursor: str | None = None,
    ) -> ForecastPageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        offset = _offset(cursor)
        items = _v2(request).forecasts(
            taxonomy_version=version,
            context=context,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            genre_id=None,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return ForecastPageV2(
            taxonomy_version=version,
            context=context,
            items=visible,
            page=page,
        )

    @router.get(
        "/forecast/next-up",
        response_model=NextUpPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read the precomputed family-validated next-up ranking",
    )
    def next_up(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = "ready",
        context: ComparisonContextV2 = "global",
        limit: V2Limit = 20,
        cursor: str | None = None,
    ) -> NextUpPageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        offset = _offset(cursor)
        items = _v2(request).next_up(
            taxonomy_version=version,
            context=context,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return NextUpPageV2(
            taxonomy_version=version,
            context=context,
            items=visible,
            page=page,
        )

    @router.get(
        "/ecosystem",
        response_model=list[EcosystemPointV2],
        responses=V2_ERROR_RESPONSES,
        summary="Read global or macro-family ecosystem health",
    )
    def ecosystem(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        macro_family_id: str | None = None,
        context: ComparisonContextV2 = "global",
        weeks: V2Weeks = 26,
    ) -> tuple[EcosystemPointV2, ...]:
        _cache_headers(response, cache_ttl_seconds)
        catalog = _taxonomy(request)
        version = _version(catalog, taxonomy_version)
        _validate_filter_ids(catalog, macro_family_id, None)
        return _v2(request).ecosystem(
            taxonomy_version=version,
            context=context,
            macro_family_id=macro_family_id,
            weeks=weeks,
        )

    @router.get(
        "/briefs",
        response_model=CreatorBriefPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read materialized taxonomy-v2 creator briefs",
    )
    def briefs(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        week: date | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = "ready",
        context: ComparisonContextV2 = "global",
        limit: V2Limit = 50,
        cursor: str | None = None,
    ) -> CreatorBriefPageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        repository = _v2(request)
        selected_week = _selected_week(
            week,
            repository.latest_brief_week(version, context),
        )
        offset = _offset(cursor)
        if selected_week is None:
            return CreatorBriefPageV2(
                taxonomy_version=version,
                week=None,
                context=context,
                items=(),
                page=CursorPageMeta(next_cursor=None, has_more=False),
            )
        items = repository.briefs(
            taxonomy_version=version,
            week=selected_week,
            context=context,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return CreatorBriefPageV2(
            taxonomy_version=version,
            week=selected_week,
            context=context,
            items=visible,
            page=page,
        )

    @router.get(
        "/scene-map",
        response_model=SceneMapPageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read the precomputed taxonomy-v2 scene projection",
    )
    def scene_map(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        week: date | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = None,
        context: ComparisonContextV2 = "global",
        limit: V2Limit = 100,
        cursor: str | None = None,
    ) -> SceneMapPageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        repository = _v2(request)
        selected_week = _selected_week(
            week,
            repository.latest_scene_week(version, context),
        )
        offset = _offset(cursor)
        if selected_week is None:
            return SceneMapPageV2(
                taxonomy_version=version,
                as_of_week=None,
                context=context,
                items=(),
                page=CursorPageMeta(next_cursor=None, has_more=False),
            )
        items = repository.scene_map(
            taxonomy_version=version,
            week=selected_week,
            context=context,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return SceneMapPageV2(
            taxonomy_version=version,
            as_of_week=selected_week,
            context=context,
            items=visible,
            page=page,
        )

    @router.get(
        "/coverage",
        response_model=CoveragePageV2,
        responses=V2_ERROR_RESPONSES,
        summary="Read source coverage, missingness, and eligibility",
    )
    def coverage(
        request: Request,
        response: Response,
        taxonomy_version: str | None = None,
        week: date | None = None,
        macro_family_id: str | None = None,
        parent_genre_id: str | None = None,
        eligibility_state: CoverageStatusV2 | None = None,
        limit: V2Limit = 50,
        cursor: str | None = None,
    ) -> CoveragePageV2:
        _cache_headers(response, cache_ttl_seconds)
        _catalog, version = _validated_scope(
            request,
            taxonomy_version,
            macro_family_id,
            parent_genre_id,
        )
        repository = _v2(request)
        selected_week = _selected_week(
            week,
            repository.latest_coverage_week(version),
        )
        offset = _offset(cursor)
        if selected_week is None:
            return CoveragePageV2(
                taxonomy_version=version,
                week=None,
                items=(),
                page=CursorPageMeta(next_cursor=None, has_more=False),
            )
        items = repository.coverage(
            taxonomy_version=version,
            week=selected_week,
            macro_family_id=macro_family_id,
            parent_genre_id=parent_genre_id,
            eligibility_state=eligibility_state,
            limit=limit + 1,
            offset=offset,
        )
        visible, page = _fetched_page(items, offset, limit)
        return CoveragePageV2(
            taxonomy_version=version,
            week=selected_week,
            items=visible,
            page=page,
        )

    return router


def _repository(request: Request) -> DuckDBReadRepository:
    value = request.app.state.repository
    if not isinstance(value, DuckDBReadRepository):
        raise RuntimeError("API repository is not initialized")
    return value


def _v2(request: Request) -> DuckDBV2Repository:
    return _repository(request).v2


def _taxonomy(request: Request) -> GenreTaxonomy:
    value = request.app.state.taxonomy
    if not isinstance(value, GenreTaxonomy):
        raise RuntimeError("taxonomy is not initialized")
    return value


def _cache(request: Request) -> TTLResponseCache:
    value = request.app.state.response_cache
    if not isinstance(value, TTLResponseCache):
        raise RuntimeError("API response cache is not initialized")
    return value


def _version(catalog: GenreTaxonomy, requested: str | None) -> str:
    if requested is None:
        return catalog.taxonomy_version
    if requested != catalog.taxonomy_version:
        _raise(
            422,
            "invalid_taxonomy_version",
            f"Unsupported taxonomy version: {requested}",
        )
    return requested


def _known_genre(catalog: GenreTaxonomy, genre_id: str) -> None:
    if genre_id not in catalog.genre_by_id:
        _raise(404, "unknown_genre_id", f"Unknown genre_id: {genre_id}")


def _validate_filter_ids(
    catalog: GenreTaxonomy,
    macro_family_id: str | None,
    parent_genre_id: str | None,
) -> None:
    family_ids = {
        family.macro_family_id for family in catalog.macro_families
    }
    if macro_family_id is not None and macro_family_id not in family_ids:
        _raise(
            404,
            "unknown_macro_family_id",
            f"Unknown macro_family_id: {macro_family_id}",
        )
    if parent_genre_id is not None:
        _known_genre(catalog, parent_genre_id)


def _validated_scope(
    request: Request,
    taxonomy_version: str | None,
    macro_family_id: str | None,
    parent_genre_id: str | None,
) -> tuple[GenreTaxonomy, str]:
    catalog = _taxonomy(request)
    version = _version(catalog, taxonomy_version)
    _validate_filter_ids(catalog, macro_family_id, parent_genre_id)
    return catalog, version


def _catalog(
    catalog: GenreTaxonomy,
    statuses: dict[str, CoverageStatusV2],
    *,
    macro_family_id: str | None,
    parent_genre_id: str | None,
    eligibility_state: CoverageStatusV2 | None,
    query: str | None = None,
) -> tuple[GenreIdentityV2, ...]:
    normalized_query = None if query is None else normalize_alias(query)
    repository_family_names = {
        family.macro_family_id: family.display_name
        for family in catalog.macro_families
    }
    items: list[GenreIdentityV2] = []
    for genre in catalog.genres:
        coverage = statuses.get(genre.genre_id, "not_observed")
        if macro_family_id is not None and genre.macro_family_id != macro_family_id:
            continue
        if parent_genre_id is not None and genre.parent_genre_id != parent_genre_id:
            continue
        if eligibility_state is not None and coverage != eligibility_state:
            continue
        if normalized_query is not None and not any(
            normalized_query in normalize_alias(value)
            for value in genre.all_aliases
        ):
            continue
        items.append(
            GenreIdentityV2(
                genre_id=genre.genre_id,
                slug=genre.slug,
                display_name=genre.display_name,
                macro_family_id=genre.macro_family_id,
                macro_family_name=repository_family_names[
                    genre.macro_family_id
                ],
                parent_genre_id=genre.parent_genre_id,
                taxonomy_version=genre.taxonomy_version,
                taxonomy_status=genre.status,
                coverage_status=coverage,
            )
        )
    return tuple(items)


def _selected_week(requested: date | None, latest: date | None) -> date | None:
    if requested is not None:
        _validate_week(requested)
        return requested
    return latest


def _validate_week(week: date) -> None:
    if week.weekday() != 0:
        _raise(
            422,
            "invalid_iso_week",
            "week must be the Monday starting an ISO week",
        )
    if week > _current_iso_week():
        _raise(422, "future_week", "future ISO weeks are not available")


def _current_iso_week() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


def _offset(cursor: str | None) -> int:
    try:
        return decode_cursor(cursor)
    except ValueError:
        _raise(422, "invalid_cursor", "Cursor is invalid or expired")


def _slice_page[T](
    items: tuple[T, ...],
    offset: int,
    limit: int,
) -> tuple[tuple[T, ...], CursorPageMeta]:
    return _fetched_page(items[offset : offset + limit + 1], offset, limit)


def _fetched_page[T](
    items: tuple[T, ...],
    offset: int,
    limit: int,
) -> tuple[tuple[T, ...], CursorPageMeta]:
    has_more = len(items) > limit
    return (
        items[:limit],
        CursorPageMeta(
            next_cursor=encode_cursor(offset + limit) if has_more else None,
            has_more=has_more,
        ),
    )


def _raise(status_code: int, code: str, message: str) -> Never:
    raise HTTPException(
        status_code=status_code,
        detail=ApiErrorDetail(code=code, message=message).model_dump(
            mode="json"
        ),
    )


def _cache_headers(response: Response, ttl_seconds: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={ttl_seconds}"
