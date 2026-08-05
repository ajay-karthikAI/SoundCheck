"""Generate deterministic, evidence-linked creator briefs without an LLM API."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from soundcheck.briefs.models import (
    BriefArtistEvidence,
    BriefBatch,
    BriefCandidate,
    BriefEvidence,
    BriefSceneGenre,
    BriefSourceBundle,
    GeneratedBrief,
)
from soundcheck.briefs.storage import DuckDBBriefStore

DEFAULT_MINIMUM_EFFECTIVE_N = 5.0
MINIMUM_REFERENCE_ARTISTS = 2
MAXIMUM_SNIPPET_CHARACTERS = 180
_WHITESPACE = re.compile(r"\s+")

_HEADLINES = (
    "{genre} has room to move before the release lane fills",
    "The opening in {genre}: audience pull is beating release pressure",
    "{genre} is moving with more demand than supply",
)
_OPENINGS = (
    "{genre} closes the week at {opportunity} opportunity "
    "(90% CI {opportunity_interval}).",
    "There is real daylight around {genre}: opportunity is {opportunity}, "
    "with a 90% CI of {opportunity_interval}.",
    "The current {genre} opening measures {opportunity} "
    "(90% CI {opportunity_interval}).",
)
_FORECASTS = (
    "Next week's opportunity direction is {gain} "
    "(80% prediction interval {gain_interval}); {calibration}",
    "The one-week read moves {gain}, with an 80% prediction interval of "
    "{gain_interval}; {calibration}",
    "The forward signal adds {gain} opportunity next week "
    "(80% prediction interval {gain_interval}); {calibration}",
)
_EVIDENCE = (
    "The listening receipts are led by {artists}. The cleanest social tell is "
    "“{snippet}”",
    "On listening, {artists} are doing the pulling. Conversation is still "
    "summed up best by “{snippet}”",
    "The artist-level lift sits with {artists}; the representative public post "
    "reads “{snippet}”",
)
_ANGLES = (
    "Keep the brief out of the already fuller {neighbors} lane; use those "
    "adjacencies as a boundary, not a reference.",
    "The nearby {neighbors} scenes carry more release pressure, so the sharper "
    "move is to leave audible daylight between them and this work.",
    "Avoid chasing the crowded cues around {neighbors}. The opportunity is in "
    "what those adjacent scenes are not supplying.",
)


class BriefSettings(BaseModel):
    """Validated CLI settings for one deterministic brief batch."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/soundcheck.duckdb")
    week_start: date | None = None
    minimum_effective_n: float = Field(
        default=DEFAULT_MINIMUM_EFFECTIVE_N,
        gt=0,
    )


def generate_briefs(
    source: BriefSourceBundle,
    *,
    created_at: datetime,
    minimum_effective_n: float = DEFAULT_MINIMUM_EFFECTIVE_N,
) -> BriefBatch:
    """Compose scene-aware notes and explicitly count every suppression."""
    if minimum_effective_n <= 0:
        msg = "minimum_effective_n must be positive"
        raise ValueError(msg)
    generated: list[GeneratedBrief] = []
    suppressed_effective_n = 0
    suppressed_thin_evidence = 0
    for candidate in source.candidates:
        if min(
            candidate.conversation_effective_n,
            candidate.supply_effective_n,
        ) < minimum_effective_n:
            suppressed_effective_n += 1
            continue
        evidence = source.evidence_by_genre.get(
            candidate.canonical_genre
        )
        neighbors = _crowded_neighbors(candidate, source.scene_genres)
        if (
            evidence is None
            or len(evidence.artists) < MINIMUM_REFERENCE_ARTISTS
            or evidence.conversation is None
            or candidate.typical_releases is None
            or candidate.release_history_weeks == 0
            or not neighbors
        ):
            suppressed_thin_evidence += 1
            continue
        generated.append(
            _compose_brief(
                candidate,
                evidence,
                neighbors,
                created_at=created_at,
            )
        )
    return BriefBatch(
        briefs=tuple(generated),
        candidate_count=len(source.candidates),
        suppressed_effective_n=suppressed_effective_n,
        suppressed_thin_evidence=suppressed_thin_evidence,
    )


def _compose_brief(
    candidate: BriefCandidate,
    evidence: BriefEvidence,
    neighbors: tuple[BriefSceneGenre, ...],
    *,
    created_at: datetime,
) -> GeneratedBrief:
    conversation = evidence.conversation
    if conversation is None:
        msg = "brief composition requires conversation evidence"
        raise ValueError(msg)
    indices = _template_indices(candidate)
    genre = _display_genre(candidate.canonical_genre)
    if candidate.skill_status == "no_skill":
        calibration = (
            "this is the published naive baseline (“no skill”), not a "
            "validated model edge"
        )
    elif candidate.gain_interval_low > 0:
        calibration = "the full interval stays above zero"
    else:
        calibration = (
            "the interval crosses zero, so treat the direction as promising "
            "rather than settled"
        )
    opening = _OPENINGS[indices[1]].format(
        genre=genre,
        opportunity=_signed(candidate.opportunity),
        opportunity_interval=_interval(
            candidate.opportunity_ci_low,
            candidate.opportunity_ci_high,
        ),
    )
    forecast = _FORECASTS[indices[2]].format(
        gain=_signed(candidate.predicted_gain),
        gain_interval=_interval(
            candidate.gain_interval_low,
            candidate.gain_interval_high,
        ),
        calibration=calibration,
    )
    artists = ", ".join(
        _artist_phrase(artist) for artist in evidence.artists[:3]
    )
    snippet = _truncate(conversation.text)
    receipts = _EVIDENCE[indices[3]].format(
        artists=artists,
        snippet=snippet,
    )
    supply = _supply_context(candidate)
    neighbor_names = _human_join(
        tuple(_display_genre(item.canonical_genre) for item in neighbors)
    )
    angle = _ANGLES[indices[4]].format(neighbors=neighbor_names)
    rationale = " ".join((opening, forecast, receipts + ".", supply, angle))
    artist_names = _human_join(
        tuple(artist.artist_name for artist in evidence.artists[:3])
    )
    actions = (
        (
            f"Build the creative reference around the audience pull visible in "
            f"{artist_names}, without copying their surface cues."
        ),
        (
            f"Keep arrangement and visual language clear of the fuller "
            f"{neighbor_names} lane."
        ),
        _timing_action(candidate),
    )
    return GeneratedBrief(
        brief_id=_brief_id(candidate),
        week_start=candidate.week_start,
        canonical_genre=candidate.canonical_genre,
        headline=_HEADLINES[indices[0]].format(genre=genre),
        opportunity=candidate.opportunity,
        opportunity_ci_low=candidate.opportunity_ci_low,
        opportunity_ci_high=candidate.opportunity_ci_high,
        rationale=rationale,
        recommended_actions=actions,
        evidence_uris=_evidence_uris(evidence),
        created_at=created_at,
    )


def _crowded_neighbors(
    candidate: BriefCandidate,
    scene_genres: tuple[BriefSceneGenre, ...],
) -> tuple[BriefSceneGenre, ...]:
    target = next(
        (
            item
            for item in scene_genres
            if item.canonical_genre == candidate.canonical_genre
        ),
        None,
    )
    if target is None or not target.embedding:
        return ()
    ranked = sorted(
        (
            (_cosine(target.embedding, item.embedding), item)
            for item in scene_genres
            if item.canonical_genre != target.canonical_genre
            and item.embedding
            and item.supply_index > 0
        ),
        key=lambda pair: (
            pair[0],
            pair[1].supply_index,
            pair[1].supply_release_groups,
            pair[1].canonical_genre,
        ),
        reverse=True,
    )
    crowded = [item for similarity, item in ranked if similarity > 0]
    return tuple(crowded[:2])


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _template_indices(candidate: BriefCandidate) -> tuple[int, ...]:
    digest = hashlib.sha256(
        f"{candidate.week_start}:{candidate.canonical_genre}".encode()
    ).digest()
    sizes = (
        len(_HEADLINES),
        len(_OPENINGS),
        len(_FORECASTS),
        len(_EVIDENCE),
        len(_ANGLES),
    )
    return tuple(
        value % size
        for value, size in zip(digest[: len(sizes)], sizes, strict=True)
    )


def _supply_context(candidate: BriefCandidate) -> str:
    typical = candidate.typical_releases
    low = candidate.release_range_low
    high = candidate.release_range_high
    if typical is None or low is None or high is None:
        return "Release velocity has no stable prior-week comparison yet."
    return (
        f"{candidate.supply_release_groups} release groups landed last week "
        f"versus a typical {typical:.1f}; the observed prior-week range is "
        f"{low}-{high} across {candidate.release_history_weeks} weeks."
    )


def _timing_action(candidate: BriefCandidate) -> str:
    if (
        candidate.typical_releases is not None
        and candidate.supply_release_groups < candidate.typical_releases
    ):
        return "Use the current low-supply window; do not wait for the release lane to refill."
    return (
        "Stage the release against a quieter adjacent week instead of adding "
        "to current crowding."
    )


def _artist_phrase(artist: BriefArtistEvidence) -> str:
    return (
        f"{artist.artist_name} (+{artist.listeners_delta:,} listeners, "
        f"+{artist.playcount_delta:,} plays)"
    )


def _evidence_uris(evidence: BriefEvidence) -> tuple[str, ...]:
    values = [
        evidence.conversation.post_uri
        if evidence.conversation is not None
        else "",
        *(
            f"https://www.last.fm/music/{quote(artist.artist_name, safe='')}"
            for artist in evidence.artists[:3]
        ),
        *(
            "https://musicbrainz.org/release-group/"
            f"{release.release_group_mbid}"
            for release in evidence.releases
        ),
    ]
    return tuple(dict.fromkeys(value for value in values if value))


def _brief_id(candidate: BriefCandidate) -> str:
    iso = candidate.week_start.isocalendar()
    slug = candidate.canonical_genre.replace(" ", "-")
    return f"{iso.year}-W{iso.week:02d}-{slug}"


def _display_genre(value: str) -> str:
    return value.replace("dnb", "drum and bass").title()


def _signed(value: float) -> str:
    return f"{value:+.2f}"


def _interval(lower: float, upper: float) -> str:
    return f"{_signed(lower)} to {_signed(upper)}"


def _truncate(value: str) -> str:
    normalized = _WHITESPACE.sub(" ", value).strip()
    if len(normalized) <= MAXIMUM_SNIPPET_CHARACTERS:
        return normalized
    shortened = normalized[: MAXIMUM_SNIPPET_CHARACTERS - 1].rsplit(
        " ",
        1,
    )[0]
    return shortened.rstrip(".,;:!?") + "…"


def _human_join(values: tuple[str, ...]) -> str:
    if not values:
        return "no adjacent genre"
    if len(values) == 1:
        return values[0]
    return f"{', '.join(values[:-1])} and {values[-1]}"


async def async_main(settings: BriefSettings) -> BriefBatch:
    """Load stored signals, generate notes, and replace one weekly batch."""
    store = DuckDBBriefStore(settings.database_path)
    await store.initialize()
    selected_week = settings.week_start or await store.latest_complete_week()
    if selected_week is None:
        return BriefBatch(
            briefs=(),
            candidate_count=0,
            suppressed_effective_n=0,
            suppressed_thin_evidence=0,
        )
    source = await store.load_sources(selected_week)
    batch = generate_briefs(
        source,
        created_at=datetime.now(UTC),
        minimum_effective_n=settings.minimum_effective_n,
    )
    await store.replace(selected_week, batch.briefs)
    return batch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/soundcheck.duckdb"),
    )
    parser.add_argument("--week", type=date.fromisoformat)
    parser.add_argument(
        "--minimum-effective-n",
        type=float,
        default=DEFAULT_MINIMUM_EFFECTIVE_N,
    )
    return parser


def main() -> None:
    """CLI entrypoint."""
    args = _build_parser().parse_args()
    batch = asyncio.run(
        async_main(
            BriefSettings(
                database_path=args.database,
                week_start=args.week,
                minimum_effective_n=args.minimum_effective_n,
            )
        )
    )
    print(
        json.dumps(
            {
                "event": "briefs_complete",
                "brief_rows": len(batch.briefs),
                "candidates": batch.candidate_count,
                "suppressed_effective_n": batch.suppressed_effective_n,
                "suppressed_thin_evidence": batch.suppressed_thin_evidence,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
