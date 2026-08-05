"""Hierarchical, multilingual, multi-membership genre resolution for taxonomy v2."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from soundcheck.resolve.genres import TextEmbedder, _cosine_similarity
from soundcheck.taxonomy import (
    GenreDefinition,
    GenreTaxonomy,
    normalize_alias,
)

DEFAULT_RESOLUTION_V2_CONFIG_PATH = Path("config/resolution_v2.yml")
ResolutionMethod = Literal[
    "manual_override",
    "exact_alias",
    "exact_multilingual_alias",
    "embedding",
    "ambiguous_exact",
    "rejected_alias",
    "below_floor",
    "explicit_other",
    "explicit_unresolved",
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


class EmbeddingResolutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cosine_floor: float = Field(ge=-1.0, le=1.0)
    multi_membership_margin: float = Field(ge=0.0, le=1.0)
    max_memberships: int = Field(ge=1, le=10)
    softmax_temperature: float = Field(gt=0.0, le=1.0)


class ActivationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_labeled_examples_per_family: int = Field(ge=1)
    minimum_precision: float = Field(ge=0.0, le=1.0)
    minimum_recall: float = Field(ge=0.0, le=1.0)
    minimum_mbid_precision: float = Field(ge=0.0, le=1.0)
    minimum_overall_precision: float = Field(ge=0.0, le=1.0)


class ResolutionV2Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    taxonomy_version: str
    embedding: EmbeddingResolutionConfig
    source_weights: dict[str, float]
    activation: ActivationThresholds

    @field_validator("source_weights")
    @classmethod
    def validate_source_weights(cls, values: dict[str, float]) -> dict[str, float]:
        required = {"lastfm", "musicbrainz_genre", "musicbrainz_tag"}
        if set(values) != required:
            raise ValueError(f"source_weights must contain exactly {sorted(required)}")
        if any(weight <= 0 or weight > 1 for weight in values.values()):
            raise ValueError("source weights must be within (0, 1]")
        return dict(sorted(values.items()))


def load_resolution_v2_config(
    path: Path = DEFAULT_RESOLUTION_V2_CONFIG_PATH,
) -> ResolutionV2Config:
    return ResolutionV2Config.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


class SourceTagV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_system: str
    source_tag: str


class GenreTagMappingV2(BaseModel):
    """One weighted mapping; a source tag may produce multiple rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_system: str
    source_tag: str
    normalized_source_tag: str
    canonical_genre_id: str
    macro_family_id: str
    parent_genre_id: str | None
    membership_weight: float = Field(ge=0.0, le=1.0)
    method: ResolutionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    language: str
    model_name: str
    taxonomy_version: str
    resolved_at: datetime

    _resolved_at_utc = field_validator("resolved_at")(_as_utc)


class CanonicalGenreEmbeddingV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_genre_id: str
    macro_family_id: str
    parent_genre_id: str | None
    embedding: tuple[float, ...]
    model_name: str
    taxonomy_version: str
    embedded_at: datetime

    _embedded_at_utc = field_validator("embedded_at")(_as_utc)


class ArtistTagEvidenceV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artist_key_type: Literal["mbid", "name"]
    artist_key: str
    artist_mbid: str | None
    artist_name: str
    source_system: str
    source_tag: str
    evidence_at: datetime

    _evidence_at_utc = field_validator("evidence_at")(_as_utc)


class ArtistGenreMembershipV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artist_key_type: Literal["mbid", "name"]
    artist_key: str
    artist_mbid: str | None
    artist_name: str
    canonical_genre_id: str
    macro_family_id: str
    parent_genre_id: str | None
    membership_weight: float = Field(ge=0.0, le=1.0)
    method: ResolutionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    source_systems: tuple[str, ...]
    source_tags: tuple[str, ...]
    input_fingerprint: str
    taxonomy_version: str
    resolved_at: datetime

    _resolved_at_utc = field_validator("resolved_at")(_as_utc)


class ArtistResolutionStateV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artist_key: str
    input_fingerprint: str


class GenreResolutionV2Batch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag_mappings: tuple[GenreTagMappingV2, ...]
    embeddings: tuple[CanonicalGenreEmbeddingV2, ...]
    artist_memberships: tuple[ArtistGenreMembershipV2, ...]
    changed_artist_fingerprints: dict[str, str]


class GenreResolutionV2Store(Protocol):
    async def initialize(self) -> None: ...

    async def load_unmapped_source_tags(
        self,
        taxonomy_version: str,
    ) -> tuple[SourceTagV2, ...]: ...

    async def load_tag_mappings(
        self,
        taxonomy_version: str,
    ) -> tuple[GenreTagMappingV2, ...]: ...

    async def load_embedding_ids(
        self,
        taxonomy_version: str,
        model_name: str,
    ) -> frozenset[str]: ...

    async def load_artist_evidence(self) -> tuple[ArtistTagEvidenceV2, ...]: ...

    async def load_artist_states(
        self,
        taxonomy_version: str,
    ) -> tuple[ArtistResolutionStateV2, ...]: ...

    async def persist_tag_resolution(
        self,
        mappings: Sequence[GenreTagMappingV2],
        embeddings: Sequence[CanonicalGenreEmbeddingV2],
    ) -> tuple[int, int]: ...

    async def persist_artist_memberships(
        self,
        memberships: Sequence[ArtistGenreMembershipV2],
        changed_artist_fingerprints: Mapping[str, str],
        *,
        taxonomy_version: str,
        resolved_at: datetime,
    ) -> int: ...


@dataclass(frozen=True)
class _AliasMatch:
    genre_id: str
    language: str
    multilingual: bool


def _alias_indexes(
    taxonomy: GenreTaxonomy,
) -> tuple[dict[str, tuple[_AliasMatch, ...]], set[str]]:
    matches: dict[str, set[_AliasMatch]] = defaultdict(set)
    rejected: set[str] = set()
    for genre in taxonomy.genres:
        labels = (
            genre.display_name,
            genre.slug,
            *genre.aliases,
            *genre.lastfm_spelling_variants,
            *genre.musicbrainz_spelling_variants,
        )
        for label in labels:
            normalized = normalize_alias(label)
            if genre.status == "rejected":
                rejected.add(normalized)
            else:
                matches[normalized].add(
                    _AliasMatch(
                        genre_id=genre.genre_id,
                        language="und",
                        multilingual=False,
                    )
                )
        for language, aliases in genre.multilingual_aliases.items():
            for alias in aliases:
                normalized = normalize_alias(alias)
                if genre.status == "rejected":
                    rejected.add(normalized)
                else:
                    matches[normalized].add(
                        _AliasMatch(
                            genre_id=genre.genre_id,
                            language=language,
                            multilingual=True,
                        )
                    )
    return (
        {
            key: tuple(
                sorted(
                    values,
                    key=lambda value: (
                        value.genre_id,
                        value.language,
                        value.multilingual,
                    ),
                )
            )
            for key, values in matches.items()
        },
        rejected,
    )


def _mapping(
    source_tag: SourceTagV2,
    genre: GenreDefinition,
    *,
    weight: float,
    method: ResolutionMethod,
    confidence: float,
    language: str,
    model_name: str,
    taxonomy_version: str,
    resolved_at: datetime,
) -> GenreTagMappingV2:
    return GenreTagMappingV2(
        source_system=source_tag.source_system,
        source_tag=source_tag.source_tag,
        normalized_source_tag=normalize_alias(source_tag.source_tag),
        canonical_genre_id=genre.genre_id,
        macro_family_id=genre.macro_family_id,
        parent_genre_id=genre.parent_genre_id,
        membership_weight=weight,
        method=method,
        confidence=confidence,
        language=language,
        model_name=model_name,
        taxonomy_version=taxonomy_version,
        resolved_at=resolved_at,
    )


def resolve_source_tag_v2(
    source_tag: SourceTagV2,
    taxonomy: GenreTaxonomy,
    config: ResolutionV2Config,
    *,
    canonical_vectors: Mapping[str, tuple[float, ...]],
    source_vector: tuple[float, ...] | None,
    model_name: str,
    resolved_at: datetime,
) -> tuple[GenreTagMappingV2, ...]:
    """Apply override, exact, then embedding precedence without forced matches."""

    genres = taxonomy.genre_by_id
    normalized = normalize_alias(source_tag.source_tag)
    manual_overrides = {
        normalize_alias(alias): genre_id
        for alias, genre_id in (
            taxonomy.production_compatibility.manual_overrides.items()
        )
    }
    override_id = manual_overrides.get(normalized)
    if override_id is not None:
        return (
            _mapping(
                source_tag,
                genres[override_id],
                weight=1.0,
                method="manual_override",
                confidence=1.0,
                language="und",
                model_name=model_name,
                taxonomy_version=taxonomy.taxonomy_version,
                resolved_at=resolved_at,
            ),
        )
    aliases, rejected = _alias_indexes(taxonomy)
    exact = aliases.get(normalized, ())
    exact_ids = {match.genre_id for match in exact}
    if len(exact_ids) == 1:
        genre_id = next(iter(exact_ids))
        match = next(match for match in exact if match.genre_id == genre_id)
        if genre_id == taxonomy.other_genre_id:
            method: ResolutionMethod = "explicit_other"
        elif genre_id == taxonomy.unresolved_genre_id:
            method = "explicit_unresolved"
        else:
            method = (
                "exact_multilingual_alias" if match.multilingual else "exact_alias"
            )
        return (
            _mapping(
                source_tag,
                genres[genre_id],
                weight=1.0,
                method=method,
                confidence=1.0,
                language=match.language,
                model_name=model_name,
                taxonomy_version=taxonomy.taxonomy_version,
                resolved_at=resolved_at,
            ),
        )
    if len(exact_ids) > 1 or normalized in rejected:
        method = "ambiguous_exact" if len(exact_ids) > 1 else "rejected_alias"
        return (
            _mapping(
                source_tag,
                genres[taxonomy.unresolved_genre_id],
                weight=1.0,
                method=method,
                confidence=1.0,
                language="und",
                model_name=model_name,
                taxonomy_version=taxonomy.taxonomy_version,
                resolved_at=resolved_at,
            ),
        )
    if source_vector is None:
        raise ValueError("unmatched source tags require an embedding")
    similarities = sorted(
        (
            (genre_id, _cosine_similarity(source_vector, vector))
            for genre_id, vector in canonical_vectors.items()
        ),
        key=lambda item: (-item[1], item[0]),
    )
    best_similarity = similarities[0][1] if similarities else -1.0
    accepted = tuple(
        item
        for item in similarities
        if item[1] >= config.embedding.cosine_floor
        and best_similarity - item[1] <= config.embedding.multi_membership_margin
    )[: config.embedding.max_memberships]
    if not accepted:
        return (
            _mapping(
                source_tag,
                genres[taxonomy.unresolved_genre_id],
                weight=1.0,
                method="below_floor",
                confidence=max(0.0, min(1.0, best_similarity)),
                language="und",
                model_name=model_name,
                taxonomy_version=taxonomy.taxonomy_version,
                resolved_at=resolved_at,
            ),
        )
    logits = tuple(
        math.exp(
            (similarity - best_similarity)
            / config.embedding.softmax_temperature
        )
        for _genre_id, similarity in accepted
    )
    total = sum(logits)
    return tuple(
        _mapping(
            source_tag,
            genres[genre_id],
            weight=logit / total,
            method="embedding",
            confidence=max(0.0, min(1.0, similarity)),
            language="und",
            model_name=model_name,
            taxonomy_version=taxonomy.taxonomy_version,
            resolved_at=resolved_at,
        )
        for (genre_id, similarity), logit in zip(accepted, logits, strict=True)
    )


def _artist_fingerprint(evidence: Sequence[ArtistTagEvidenceV2]) -> str:
    payload = [
        {
            "source_system": item.source_system,
            "source_tag": normalize_alias(item.source_tag),
            "evidence_at": item.evidence_at.isoformat(),
        }
        for item in sorted(
            evidence,
            key=lambda item: (
                item.source_system,
                normalize_alias(item.source_tag),
                item.evidence_at,
            ),
        )
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_artist_memberships_v2(
    evidence: Sequence[ArtistTagEvidenceV2],
    mappings: Sequence[GenreTagMappingV2],
    config: ResolutionV2Config,
    *,
    resolved_at: datetime,
    existing_states: Mapping[str, str],
    unresolved_genre_id: str,
) -> tuple[tuple[ArtistGenreMembershipV2, ...], dict[str, str]]:
    """Aggregate changed artists into normalized multi-genre memberships."""

    mapping_lookup: dict[tuple[str, str], list[GenreTagMappingV2]] = defaultdict(list)
    for mapping in mappings:
        mapping_lookup[
            (mapping.source_system, mapping.normalized_source_tag)
        ].append(mapping)
    by_artist: dict[str, list[ArtistTagEvidenceV2]] = defaultdict(list)
    for item in evidence:
        by_artist[item.artist_key].append(item)
    memberships: list[ArtistGenreMembershipV2] = []
    changed: dict[str, str] = {}
    method_rank = {
        "manual_override": 0,
        "exact_alias": 1,
        "exact_multilingual_alias": 1,
        "embedding": 2,
        "explicit_other": 3,
        "explicit_unresolved": 4,
        "ambiguous_exact": 4,
        "rejected_alias": 4,
        "below_floor": 4,
    }
    for artist_key, artist_evidence in sorted(by_artist.items()):
        fingerprint = _artist_fingerprint(artist_evidence)
        if existing_states.get(artist_key) == fingerprint:
            continue
        changed[artist_key] = fingerprint
        contributions: dict[str, list[tuple[float, GenreTagMappingV2]]] = defaultdict(
            list
        )
        for item in artist_evidence:
            source_weight = config.source_weights[item.source_system]
            for mapping in mapping_lookup.get(
                (item.source_system, normalize_alias(item.source_tag)),
                (),
            ):
                score = source_weight * mapping.membership_weight
                contributions[mapping.canonical_genre_id].append((score, mapping))
        resolved_ids = set(contributions) - {unresolved_genre_id}
        if resolved_ids:
            selected = {
                genre_id: values
                for genre_id, values in contributions.items()
                if genre_id in resolved_ids
            }
        else:
            selected = contributions
        totals = {
            genre_id: sum(score for score, _mapping_item in values)
            for genre_id, values in selected.items()
        }
        denominator = sum(totals.values())
        if denominator <= 0:
            continue
        first = sorted(
            artist_evidence,
            key=lambda item: (
                item.artist_key_type != "mbid",
                item.artist_name.casefold(),
            ),
        )[0]
        for genre_id, values in sorted(selected.items()):
            evidence_mappings = [mapping for _score, mapping in values]
            representative = min(
                evidence_mappings,
                key=lambda mapping: (
                    method_rank[mapping.method],
                    -mapping.confidence,
                    mapping.source_tag,
                ),
            )
            score_total = totals[genre_id]
            confidence = sum(
                score * mapping.confidence for score, mapping in values
            ) / score_total
            memberships.append(
                ArtistGenreMembershipV2(
                    artist_key_type=first.artist_key_type,
                    artist_key=artist_key,
                    artist_mbid=first.artist_mbid,
                    artist_name=first.artist_name,
                    canonical_genre_id=genre_id,
                    macro_family_id=representative.macro_family_id,
                    parent_genre_id=representative.parent_genre_id,
                    membership_weight=score_total / denominator,
                    method=representative.method,
                    confidence=confidence,
                    source_systems=tuple(
                        sorted({mapping.source_system for mapping in evidence_mappings})
                    ),
                    source_tags=tuple(
                        sorted(
                            {mapping.source_tag for mapping in evidence_mappings},
                            key=str.casefold,
                        )
                    ),
                    input_fingerprint=fingerprint,
                    taxonomy_version=config.taxonomy_version,
                    resolved_at=resolved_at,
                )
            )
    return tuple(memberships), changed


async def resolve_genres_v2(
    store: GenreResolutionV2Store,
    taxonomy: GenreTaxonomy,
    config: ResolutionV2Config,
    embedder: TextEmbedder,
    *,
    resolved_at: datetime | None = None,
) -> tuple[int, int, int]:
    """Incrementally resolve new tags and changed artist evidence."""

    if taxonomy.taxonomy_version != config.taxonomy_version:
        raise ValueError("resolution and taxonomy versions must match")
    await store.initialize()
    resolution_time = resolved_at or datetime.now(UTC)
    canonical = tuple(
        genre
        for genre in taxonomy.genres
        if genre.status != "rejected"
        and genre.genre_id
        not in {taxonomy.other_genre_id, taxonomy.unresolved_genre_id}
    )
    vectors = await asyncio.to_thread(
        embedder.encode,
        tuple(genre.display_name for genre in canonical),
    )
    if len(vectors) != len(canonical):
        raise ValueError("embedder returned the wrong number of canonical vectors")
    vector_by_id = {
        genre.genre_id: vector
        for genre, vector in zip(canonical, vectors, strict=True)
    }
    embeddings = tuple(
        CanonicalGenreEmbeddingV2(
            canonical_genre_id=genre.genre_id,
            macro_family_id=genre.macro_family_id,
            parent_genre_id=genre.parent_genre_id,
            embedding=vector,
            model_name=embedder.model_name,
            taxonomy_version=taxonomy.taxonomy_version,
            embedded_at=resolution_time,
        )
        for genre, vector in zip(canonical, vectors, strict=True)
    )
    existing_embedding_ids = await store.load_embedding_ids(
        taxonomy.taxonomy_version,
        embedder.model_name,
    )
    embeddings_to_persist = tuple(
        embedding
        for embedding in embeddings
        if embedding.canonical_genre_id not in existing_embedding_ids
    )
    source_tags = await store.load_unmapped_source_tags(taxonomy.taxonomy_version)
    aliases, rejected = _alias_indexes(taxonomy)
    unmatched = tuple(
        tag
        for tag in source_tags
        if normalize_alias(tag.source_tag)
        not in {
            *aliases.keys(),
            *rejected,
            *(
                normalize_alias(alias)
                for alias in (
                    taxonomy.production_compatibility.manual_overrides
                )
            ),
        }
    )
    unmatched_vectors = await asyncio.to_thread(
        embedder.encode,
        tuple(tag.source_tag for tag in unmatched),
    )
    source_vectors = {
        (tag.source_system, tag.source_tag): vector
        for tag, vector in zip(unmatched, unmatched_vectors, strict=True)
    }
    new_mappings = tuple(
        mapping
        for tag in source_tags
        for mapping in resolve_source_tag_v2(
            tag,
            taxonomy,
            config,
            canonical_vectors=vector_by_id,
            source_vector=source_vectors.get((tag.source_system, tag.source_tag)),
            model_name=embedder.model_name,
            resolved_at=resolution_time,
        )
    )
    await store.persist_tag_resolution(new_mappings, embeddings_to_persist)
    all_mappings = await store.load_tag_mappings(taxonomy.taxonomy_version)
    evidence = await store.load_artist_evidence()
    states = {
        state.artist_key: state.input_fingerprint
        for state in await store.load_artist_states(taxonomy.taxonomy_version)
    }
    memberships, changed = build_artist_memberships_v2(
        evidence,
        all_mappings,
        config,
        resolved_at=resolution_time,
        existing_states=states,
        unresolved_genre_id=taxonomy.unresolved_genre_id,
    )
    artist_count = await store.persist_artist_memberships(
        memberships,
        changed,
        taxonomy_version=taxonomy.taxonomy_version,
        resolved_at=resolution_time,
    )
    return len(new_mappings), len(embeddings_to_persist), artist_count
