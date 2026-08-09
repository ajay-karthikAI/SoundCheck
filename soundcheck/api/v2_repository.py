"""Thin, parameterized reads over precomputed taxonomy-v2 artifacts."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import date
from typing import Any, Literal

import duckdb

from soundcheck.api.models import ArtistCredit, EstimateBand
from soundcheck.api.v2_models import (
    AxisModelSkillV2,
    ComparisonContextV2,
    ConversationReceiptV2,
    CoverageItemV2,
    CoverageStatusV2,
    CreatorBriefV2,
    EcosystemPointV2,
    EvidenceReceiptV2,
    EvidenceSourceV2,
    ForecastItemV2,
    GenreHistoryPointV2,
    GenreIdentityV2,
    ListeningReceiptV2,
    NaiveBaselineV2,
    NextUpItemV2,
    OpportunityDiagnosticsV2,
    OpportunityItemV2,
    SceneMapPointV2,
    SpikeFlagsV2,
    SupplyReceiptV2,
    TrendAxisV2,
    ValidationScoreV2,
)
from soundcheck.sql.loader import load_sql
from soundcheck.taxonomy import GenreTaxonomy

type QueryParameters = Sequence[object]


class DuckDBV2Repository:
    """Serve v2 artifacts through the worker's existing read-only connection."""

    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        lock: threading.Lock,
        taxonomy: GenreTaxonomy,
    ) -> None:
        self._connection = connection
        self._lock = lock
        self._taxonomy = taxonomy
        self._family_names = {
            family.macro_family_id: family.display_name
            for family in taxonomy.macro_families
        }

    def latest_coverage_week(self, taxonomy_version: str) -> date | None:
        return _date_or_none(
            self._one(
                "api_v2_latest_coverage_week.sql",
                (taxonomy_version,),
            )[0]
        )

    def coverage_statuses(
        self,
        taxonomy_version: str,
        week: date | None = None,
    ) -> dict[str, CoverageStatusV2]:
        selected_week = week or self.latest_coverage_week(taxonomy_version)
        if selected_week is None:
            return {}
        return {
            row[0]: row[1]
            for row in self._all(
                "api_v2_coverage_statuses.sql",
                (taxonomy_version, selected_week),
            )
        }

    def identity(
        self,
        genre_id: str,
        coverage_status: CoverageStatusV2 = "not_observed",
    ) -> GenreIdentityV2:
        genre = self._taxonomy.genre_by_id[genre_id]
        return GenreIdentityV2(
            genre_id=genre.genre_id,
            slug=genre.slug,
            display_name=genre.display_name,
            macro_family_id=genre.macro_family_id,
            macro_family_name=self._family_names[genre.macro_family_id],
            parent_genre_id=genre.parent_genre_id,
            taxonomy_version=genre.taxonomy_version,
            taxonomy_status=genre.status,
            coverage_status=coverage_status,
        )

    def latest_opportunity_week(
        self,
        taxonomy_version: str,
        context: ComparisonContextV2,
    ) -> date | None:
        return _date_or_none(
            self._one(
                "api_v2_latest_opportunity_week.sql",
                (taxonomy_version, context),
            )[0]
        )

    def opportunities(
        self,
        *,
        taxonomy_version: str,
        week: date,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[OpportunityItemV2, ...]:
        rows = self._all(
            "api_v2_opportunities.sql",
            (
                taxonomy_version,
                week,
                context,
                context,
                taxonomy_version,
                week,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                limit,
                offset,
            ),
        )
        return tuple(
            OpportunityItemV2(
                genre=self.identity(row[0], row[2]),
                week=row[1],
                context=context,
                estimate_status=row[3],
                opportunity=_optional_band(row[4], row[5], row[6]),
                discovery_gap=_optional_band(row[7], row[8], row[9]),
                conversation=_optional_band(row[10], row[11], row[12]),
                listening=_optional_band(row[13], row[14], row[15]),
                supply=_optional_band(row[16], row[17], row[18]),
                diagnostics=OpportunityDiagnosticsV2(
                    conversation_effective_n=row[19],
                    listening_effective_n=row[20],
                    supply_effective_n=row[21],
                    conversation_shrinkage_weight=row[22],
                    listening_shrinkage_weight=row[23],
                    supply_shrinkage_weight=row[24],
                ),
                spike_flags=SpikeFlagsV2(
                    conversation=row[25],
                    listening=row[26],
                    supply=row[27],
                ),
                breakout_flag=row[28],
            )
            for row in rows
        )

    def genre_history(
        self,
        *,
        taxonomy_version: str,
        genre_id: str,
        context: ComparisonContextV2,
        weeks: int,
    ) -> tuple[GenreHistoryPointV2, ...]:
        rows = self._all(
            "api_v2_genre_history.sql",
            (
                taxonomy_version,
                genre_id,
                weeks,
                taxonomy_version,
                genre_id,
                context,
                taxonomy_version,
                genre_id,
            ),
        )
        return tuple(_history_point(row) for row in rows)

    def forecasts(
        self,
        *,
        taxonomy_version: str,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        genre_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[ForecastItemV2, ...]:
        rows = self._all(
            "api_v2_forecasts.sql",
            (
                taxonomy_version,
                taxonomy_version,
                context,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                genre_id,
                genre_id,
                limit,
                offset,
            ),
        )
        return tuple(self._forecast(row) for row in rows)

    def evidence(
        self,
        *,
        taxonomy_version: str,
        genre_id: str,
        week: date,
        source: EvidenceSourceV2,
        limit: int,
        offset: int,
    ) -> tuple[EvidenceReceiptV2, ...]:
        parameters = (taxonomy_version, genre_id, week, limit, offset)
        if source == "conversation":
            return tuple(
                ConversationReceiptV2(
                    post_uri=row[0],
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
                    membership_weight=row[11],
                    membership_method=row[12],
                    membership_confidence=row[13],
                )
                for row in self._all(
                    "api_v2_conversation_evidence.sql",
                    parameters,
                )
            )
        if source == "listening":
            listening_parameters = (
                taxonomy_version,
                taxonomy_version,
                genre_id,
                week,
                taxonomy_version,
                genre_id,
                week,
                limit,
                offset,
            )
            return tuple(
                ListeningReceiptV2(
                    artist_key=row[0],
                    artist_name=row[1],
                    artist_mbid=row[2],
                    playcount=row[3],
                    listeners=row[4],
                    previous_playcount=row[5],
                    previous_listeners=row[6],
                    playcount_delta=row[7],
                    listeners_delta=row[8],
                    fetched_at=row[9],
                    previous_fetched_at=row[10],
                    interval_days=row[11],
                    listening_window_status=row[12],
                    membership_weight=row[13],
                    membership_method=row[14],
                    membership_confidence=row[15],
                )
                for row in self._all(
                    "api_v2_listening_evidence.sql",
                    listening_parameters,
                )
            )
        return tuple(
            SupplyReceiptV2(
                release_group_mbid=row[0],
                title=row[1],
                artist_credits=tuple(
                    ArtistCredit.model_validate(credit) for credit in row[2]
                ),
                first_release_date=row[3],
                types=tuple(row[4]),
                genres=tuple(row[5]),
                fetched_at=row[6],
                membership_weight=row[7],
            )
            for row in self._all(
                "api_v2_supply_evidence.sql",
                parameters,
            )
        )

    def next_up(
        self,
        *,
        taxonomy_version: str,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[NextUpItemV2, ...]:
        rows = self._all(
            "api_v2_next_up.sql",
            (
                taxonomy_version,
                context,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                limit,
                offset,
            ),
        )
        return tuple(
            NextUpItemV2(
                genre=self.identity(row[0], row[1]),
                origin_week=row[2],
                target_week=row[3],
                context=row[4],
                rank=row[5],
                predicted_opportunity=_band(row[6], row[7], row[8]),
                predicted_gain=_band(row[9], row[10], row[11]),
                conversation=AxisModelSkillV2(
                    model=row[12],
                    mase=row[13],
                    coverage_80=row[14],
                    forecast_status=row[15],
                ),
                listening=AxisModelSkillV2(
                    model=row[16],
                    mase=row[17],
                    coverage_80=row[18],
                    forecast_status=row[19],
                ),
                skill_status=row[20],
            )
            for row in rows
        )

    def ecosystem(
        self,
        *,
        taxonomy_version: str,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        weeks: int,
    ) -> tuple[EcosystemPointV2, ...]:
        rows = self._all(
            "api_v2_ecosystem.sql",
            (
                taxonomy_version,
                context,
                context,
                macro_family_id,
                macro_family_id,
                weeks,
            ),
        )
        return tuple(
            EcosystemPointV2(
                taxonomy_version=row[0],
                week=row[1],
                context=(
                    "global" if row[4] == "global" else "peer_family"
                ),
                macro_family_id=None if row[4] == "global" else row[5],
                estimate_status=row[6],
                listening_entropy=_optional_band(row[7], row[8], row[9]),
                effective_genres=_optional_band(row[10], row[11], row[12]),
                conversation_hhi=_optional_band(row[13], row[14], row[15]),
                listening_top_share=_optional_band(row[16], row[17], row[18]),
                listening_top_share_k=row[19],
                scene_churn_jaccard_4w=_optional_band(
                    row[20],
                    row[21],
                    row[22],
                ),
                breakout_genre_ids=tuple(row[23]),
                eligible_genres=row[24],
            )
            for row in rows
        )

    def latest_brief_week(
        self,
        taxonomy_version: str,
        context: ComparisonContextV2,
    ) -> date | None:
        return _date_or_none(
            self._one(
                "api_v2_latest_brief_week.sql",
                (taxonomy_version, context),
            )[0]
        )

    def briefs(
        self,
        *,
        taxonomy_version: str,
        week: date,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[CreatorBriefV2, ...]:
        rows = self._all(
            "api_v2_briefs.sql",
            (
                taxonomy_version,
                week,
                context,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                limit,
                offset,
            ),
        )
        return tuple(
            CreatorBriefV2(
                genre=self.identity(row[0], row[1]),
                brief_id=row[2],
                week=row[3],
                context=row[4],
                headline=row[5],
                opportunity=_band(row[6], row[7], row[8]),
                forecast_direction=_band(row[9], row[10], row[11]),
                forecast_model=row[12],
                backtest_mase=row[13],
                backtest_coverage_80=row[14],
                rationale=row[15],
                recommended_actions=tuple(row[16]),
                evidence_uris=tuple(row[17]),
                created_at=row[18],
            )
            for row in rows
        )

    def latest_scene_week(
        self,
        taxonomy_version: str,
        context: ComparisonContextV2,
    ) -> date | None:
        return _date_or_none(
            self._one(
                "api_v2_latest_scene_week.sql",
                (taxonomy_version, context),
            )[0]
        )

    def scene_map(
        self,
        *,
        taxonomy_version: str,
        week: date,
        context: ComparisonContextV2,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[SceneMapPointV2, ...]:
        rows = self._all(
            "api_v2_scene_map.sql",
            (
                taxonomy_version,
                context,
                taxonomy_version,
                week,
                context,
                taxonomy_version,
                week,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                limit,
                offset,
            ),
        )
        return tuple(
            SceneMapPointV2(
                genre=self.identity(row[0], row[1]),
                as_of_week=row[2],
                context=row[3],
                x=row[4],
                y=row[5],
                opportunity=_optional_band(row[6], row[7], row[8]),
                discovery_gap=_optional_band(row[9], row[10], row[11]),
                evidence_volume=row[12],
            )
            for row in rows
        )

    def coverage(
        self,
        *,
        taxonomy_version: str,
        week: date,
        macro_family_id: str | None,
        parent_genre_id: str | None,
        eligibility_state: str | None,
        limit: int,
        offset: int,
    ) -> tuple[CoverageItemV2, ...]:
        rows = self._all(
            "api_v2_coverage.sql",
            (
                taxonomy_version,
                week,
                macro_family_id,
                macro_family_id,
                parent_genre_id,
                parent_genre_id,
                eligibility_state,
                eligibility_state,
                limit,
                offset,
            ),
        )
        return tuple(
            CoverageItemV2(
                genre=self.identity(row[0], row[1]),
                week=row[2],
                lastfm_tag_available=row[3],
                unique_lastfm_artists=row[4],
                artists_with_consecutive_valid_snapshots=row[5],
                lastfm_history_weeks=row[6],
                musicbrainz_release_group_count=row[7],
                resolved_bluesky_post_count=row[8],
                resolution_attempt_count=row[9],
                resolution_rate=row[10],
                cross_source_overlap_artist_count=row[11],
                cross_source_overlap=row[12],
                latest_source_timestamp=row[13],
                missing_axes=_missing_axes(row[14], row[15], row[16]),
                stale=row[17],
            )
            for row in rows
        )

    def _forecast(self, row: tuple[Any, ...]) -> ForecastItemV2:
        prediction = _optional_band(row[9], row[10], row[11])
        genre_validation = (
            None
            if prediction is None
            else ValidationScoreV2(
                mase=row[12],
                coverage_80=row[13],
                score_status=row[14],
            )
        )
        family_validation = (
            None
            if prediction is None
            else ValidationScoreV2(
                mase=row[15],
                coverage_80=row[16],
                score_status=row[17],
            )
        )
        naive_band = _optional_band(row[18], row[19], row[20])
        naive = (
            None
            if naive_band is None
            else NaiveBaselineV2(
                prediction_interval_80=naive_band,
                validation=ValidationScoreV2(
                    mase=row[21],
                    coverage_80=row[22],
                    score_status=row[23],
                ),
            )
        )
        return ForecastItemV2(
            genre=self.identity(row[0], row[1] or "not_observed"),
            origin_week=row[2],
            target_week=row[3],
            context=row[4],
            target_axis=row[5],
            horizon=row[6],
            forecast_status=row[7],
            model=row[8],
            prediction_interval_80=prediction,
            genre_validation=genre_validation,
            family_validation=family_validation,
            naive_baseline=naive,
            valid_training_weeks=row[24],
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
            raise RuntimeError(
                f"{statement_name} returned {len(rows)} rows; expected one"
            )
        return rows[0]


def _history_point(row: tuple[Any, ...]) -> GenreHistoryPointV2:
    return GenreHistoryPointV2(
        week=row[0],
        coverage_status=row[1],
        estimate_status=row[2],
        conversation=_optional_axis(*row[3:10]),
        listening=_optional_axis(*row[10:17]),
        supply=_optional_axis(*row[17:24]),
        opportunity=_optional_band(row[24], row[25], row[26]),
        discovery_gap=_optional_band(row[27], row[28], row[29]),
    )


def _optional_axis(
    point: object,
    low: object,
    high: object,
    ewma: object,
    ewma_low: object,
    ewma_high: object,
    spike: object,
) -> TrendAxisV2 | None:
    index = _optional_band(point, low, high)
    average = _optional_band(ewma, ewma_low, ewma_high)
    if index is None or average is None:
        return None
    return TrendAxisV2(index=index, ewma=average, spike=bool(spike))


def _band(point: object, lower: object, upper: object) -> EstimateBand:
    return EstimateBand.model_validate(
        {"value": point, "lower": lower, "upper": upper}
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
    raise TypeError(f"expected date or null, got {type(value).__name__}")


def _missing_axes(
    listening: object,
    conversation: object,
    supply: object,
) -> tuple[Literal["conversation", "listening", "supply"], ...]:
    axes: list[Literal["conversation", "listening", "supply"]] = []
    if conversation:
        axes.append("conversation")
    if listening:
        axes.append("listening")
    if supply:
        axes.append("supply")
    return tuple(axes)
