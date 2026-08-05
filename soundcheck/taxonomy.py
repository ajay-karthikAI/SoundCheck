"""Versioned, hierarchical music-genre taxonomy and shared loader."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

DEFAULT_TAXONOMY_PATH = Path("config/genre_canonical.yml")
GenreStatus = Literal["enabled", "candidate", "rejected"]
SourceSystem = Literal["lastfm", "musicbrainz"]
GENRE_STATUSES: tuple[GenreStatus, ...] = (
    "enabled",
    "candidate",
    "rejected",
)

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TAXONOMY_VERSION_PATTERN = re.compile(
    r"^2\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


def normalize_alias(value: str) -> str:
    """Normalize an alias without transliterating one writing system into another."""
    decomposed = unicodedata.normalize("NFKD", value.strip()).casefold()
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    words = re.sub(r"[\W_]+", " ", without_marks.replace("&", " and "))
    return " ".join(words.split())


def _validate_identifier(value: str, *, label: str) -> str:
    normalized = value.strip()
    if not _ID_PATTERN.fullmatch(normalized):
        msg = f"{label} must be a stable snake_case identifier"
        raise ValueError(msg)
    return normalized


def _validate_slug(value: str) -> str:
    normalized = value.strip()
    if not _SLUG_PATTERN.fullmatch(normalized):
        msg = "slug must contain lowercase letters, digits, and single hyphens"
        raise ValueError(msg)
    return normalized


def _validate_version(value: str) -> str:
    normalized = value.strip()
    if not _TAXONOMY_VERSION_PATTERN.fullmatch(normalized):
        msg = "taxonomy_version must be a semantic version with major version 2"
        raise ValueError(msg)
    return normalized


def _ordered_aliases(values: tuple[str, ...]) -> tuple[str, ...]:
    stripped = tuple(value.strip() for value in values)
    if any(not value for value in stripped):
        msg = "aliases cannot be blank"
        raise ValueError(msg)
    normalized = tuple(normalize_alias(value) for value in stripped)
    if any(not value for value in normalized):
        msg = "aliases must contain letters or numbers"
        raise ValueError(msg)
    representatives: dict[str, str] = {}
    for key, value in sorted(
        zip(normalized, stripped, strict=True),
        key=lambda item: (item[0], item[1].casefold(), item[1]),
    ):
        representatives.setdefault(key, value)
    return tuple(
        representatives[key]
        for key in sorted(representatives)
    )


def _source_tags_in_declared_order(values: tuple[str, ...]) -> tuple[str, ...]:
    stripped = tuple(value.strip() for value in values)
    if any(not value for value in stripped):
        msg = "collection tags cannot be blank"
        raise ValueError(msg)
    if len({value.casefold() for value in stripped}) != len(stripped):
        msg = "collection tags must be unique, ignoring case"
        raise ValueError(msg)
    return stripped


class MacroFamily(BaseModel):
    """One broad peer family in the hierarchy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    macro_family_id: str
    display_name: str
    slug: str

    @field_validator("macro_family_id")
    @classmethod
    def validate_macro_family_id(cls, value: str) -> str:
        return _validate_identifier(value, label="macro_family_id")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "macro-family display_name cannot be blank"
            raise ValueError(msg)
        return normalized

    _validate_slug = field_validator("slug")(_validate_slug)


class GenreDefinition(BaseModel):
    """One stable canonical genre, including source-specific spellings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    genre_id: str
    display_name: str
    slug: str
    macro_family_id: str
    parent_genre_id: str | None
    aliases: tuple[str, ...]
    multilingual_aliases: dict[str, tuple[str, ...]]
    lastfm_spelling_variants: tuple[str, ...]
    musicbrainz_spelling_variants: tuple[str, ...]
    status: GenreStatus
    taxonomy_version: str

    @field_validator("genre_id")
    @classmethod
    def validate_genre_id(cls, value: str) -> str:
        return _validate_identifier(value, label="genre_id")

    @field_validator("macro_family_id")
    @classmethod
    def validate_macro_family_id(cls, value: str) -> str:
        return _validate_identifier(value, label="macro_family_id")

    @field_validator("parent_genre_id")
    @classmethod
    def validate_parent_genre_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_identifier(value, label="parent_genre_id")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "genre display_name cannot be blank"
            raise ValueError(msg)
        return normalized

    _validate_slug = field_validator("slug")(_validate_slug)
    _validate_taxonomy_version = field_validator("taxonomy_version")(
        _validate_version
    )
    _order_aliases = field_validator(
        "aliases",
        "lastfm_spelling_variants",
        "musicbrainz_spelling_variants",
    )(_ordered_aliases)

    @field_validator("multilingual_aliases")
    @classmethod
    def validate_multilingual_aliases(
        cls,
        values: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        normalized: dict[str, tuple[str, ...]] = {}
        for locale, aliases in sorted(values.items()):
            if not _LOCALE_PATTERN.fullmatch(locale):
                msg = f"invalid multilingual alias locale: {locale}"
                raise ValueError(msg)
            normalized[locale] = _ordered_aliases(aliases)
        return normalized

    @property
    def canonical_name(self) -> str:
        """Return the stable lower-case label used by the current marts."""
        return self.display_name.casefold()

    @property
    def all_aliases(self) -> tuple[str, ...]:
        """Return every exact-match label, deduplicated deterministically."""
        values = (
            self.display_name,
            self.slug,
            *self.aliases,
            *self.lastfm_spelling_variants,
            *self.musicbrainz_spelling_variants,
            *(
                alias
                for locale in sorted(self.multilingual_aliases)
                for alias in self.multilingual_aliases[locale]
            ),
        )
        by_normalized: dict[str, str] = {}
        for value in values:
            by_normalized.setdefault(normalize_alias(value), value)
        return tuple(by_normalized[key] for key in sorted(by_normalized))


class ProductionCompatibility(BaseModel):
    """Frozen Phase-B views that keep current collection and metrics unchanged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_genre_ids: tuple[str, ...]
    lastfm_collection_tags: tuple[str, ...]
    musicbrainz_collection_tags: tuple[str, ...]
    manual_overrides: dict[str, str]

    @field_validator("canonical_genre_ids")
    @classmethod
    def validate_canonical_genre_ids(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(
            _validate_identifier(value, label="canonical_genre_id")
            for value in values
        )
        if len(set(normalized)) != len(normalized):
            msg = "production canonical_genre_ids must be unique"
            raise ValueError(msg)
        return normalized

    _validate_collection_tags = field_validator(
        "lastfm_collection_tags",
        "musicbrainz_collection_tags",
    )(_source_tags_in_declared_order)

    @field_validator("manual_overrides")
    @classmethod
    def validate_manual_overrides(
        cls,
        values: dict[str, str],
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for source, target in values.items():
            key = source.strip().casefold()
            if not key:
                msg = "manual override aliases cannot be blank"
                raise ValueError(msg)
            if key in normalized:
                msg = f"duplicate manual override: {source}"
                raise ValueError(msg)
            normalized[key] = _validate_identifier(
                target,
                label="manual override target",
            )
        return dict(sorted(normalized.items()))


class GenreTaxonomy(BaseModel):
    """Validated taxonomy v2 with deterministic ordering and safe fallbacks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    taxonomy_version: str
    default_genre_id: str
    other_genre_id: str
    unresolved_genre_id: str
    macro_families: tuple[MacroFamily, ...]
    genres: tuple[GenreDefinition, ...]
    production_compatibility: ProductionCompatibility

    _validate_taxonomy_version = field_validator("taxonomy_version")(
        _validate_version
    )

    @field_validator(
        "default_genre_id",
        "other_genre_id",
        "unresolved_genre_id",
    )
    @classmethod
    def validate_special_genre_id(cls, value: str) -> str:
        return _validate_identifier(value, label="special genre_id")

    @field_validator("macro_families")
    @classmethod
    def order_macro_families(
        cls,
        values: tuple[MacroFamily, ...],
    ) -> tuple[MacroFamily, ...]:
        return tuple(sorted(values, key=lambda item: item.macro_family_id))

    @field_validator("genres")
    @classmethod
    def order_genres(
        cls,
        values: tuple[GenreDefinition, ...],
    ) -> tuple[GenreDefinition, ...]:
        return tuple(sorted(values, key=lambda item: item.genre_id))

    @model_validator(mode="after")
    def validate_taxonomy(self) -> GenreTaxonomy:
        self._validate_unique_keys()
        self._validate_references()
        self._validate_hierarchy()
        self._validate_alias_ownership()
        self._validate_production_compatibility()
        return self

    def _validate_unique_keys(self) -> None:
        _require_unique(
            (family.macro_family_id for family in self.macro_families),
            label="macro_family_id",
        )
        _require_unique(
            (family.slug for family in self.macro_families),
            label="macro-family slug",
        )
        _require_unique(
            (genre.genre_id for genre in self.genres),
            label="genre_id",
        )
        _require_unique(
            (genre.slug for genre in self.genres),
            label="genre slug",
        )

    def _validate_references(self) -> None:
        family_ids = {family.macro_family_id for family in self.macro_families}
        genres = self.genre_by_id
        version_mismatches = sorted(
            genre.genre_id
            for genre in self.genres
            if genre.taxonomy_version != self.taxonomy_version
        )
        if version_mismatches:
            msg = (
                "genre taxonomy_version must match the root version: "
                f"{version_mismatches}"
            )
            raise ValueError(msg)
        invalid_families = sorted(
            {
                genre.macro_family_id
                for genre in self.genres
                if genre.macro_family_id not in family_ids
            }
        )
        if invalid_families:
            msg = f"unknown macro_family_id references: {invalid_families}"
            raise ValueError(msg)
        invalid_parents = sorted(
            {
                genre.parent_genre_id
                for genre in self.genres
                if genre.parent_genre_id is not None
                and genre.parent_genre_id not in genres
            }
        )
        if invalid_parents:
            msg = f"unknown parent_genre_id references: {invalid_parents}"
            raise ValueError(msg)
        special_ids = {
            self.default_genre_id,
            self.other_genre_id,
            self.unresolved_genre_id,
        }
        missing_special = sorted(special_ids - genres.keys())
        if missing_special:
            msg = f"unknown special genre_id references: {missing_special}"
            raise ValueError(msg)
        if len(special_ids) != 3:
            msg = "default, other, and unresolved genre IDs must be distinct"
            raise ValueError(msg)

    def _validate_hierarchy(self) -> None:
        genres = self.genre_by_id
        for genre in self.genres:
            parent_id = genre.parent_genre_id
            if parent_id is not None:
                parent = genres[parent_id]
                if parent.macro_family_id != genre.macro_family_id:
                    msg = (
                        f"parent {parent_id} must share macro family with "
                        f"{genre.genre_id}"
                    )
                    raise ValueError(msg)
            visited: set[str] = set()
            cursor: GenreDefinition | None = genre
            while cursor is not None:
                if cursor.genre_id in visited:
                    msg = f"genre hierarchy contains a cycle at {cursor.genre_id}"
                    raise ValueError(msg)
                visited.add(cursor.genre_id)
                cursor = (
                    None
                    if cursor.parent_genre_id is None
                    else genres[cursor.parent_genre_id]
                )

    def _validate_alias_ownership(self) -> None:
        owners: dict[tuple[str, str], str] = {}
        for genre in self.genres:
            for alias in genre.all_aliases:
                key = (genre.macro_family_id, normalize_alias(alias))
                owner = owners.setdefault(key, genre.genre_id)
                if owner != genre.genre_id:
                    msg = (
                        "normalized alias is assigned to multiple genres "
                        f"within {genre.macro_family_id}: {alias!r} "
                        f"({owner}, {genre.genre_id})"
                    )
                    raise ValueError(msg)

    def _validate_production_compatibility(self) -> None:
        genres = self.genre_by_id
        profile = self.production_compatibility
        invalid_ids = sorted(set(profile.canonical_genre_ids) - genres.keys())
        if invalid_ids:
            msg = f"unknown production canonical genre IDs: {invalid_ids}"
            raise ValueError(msg)
        non_enabled = sorted(
            genre_id
            for genre_id in profile.canonical_genre_ids
            if genres[genre_id].status != "enabled"
        )
        if non_enabled:
            msg = f"production canonical genres must be enabled: {non_enabled}"
            raise ValueError(msg)
        invalid_targets = sorted(
            set(profile.manual_overrides.values())
            - set(profile.canonical_genre_ids)
        )
        if invalid_targets:
            msg = f"manual overrides target non-production genres: {invalid_targets}"
            raise ValueError(msg)
        for source, target_id in profile.manual_overrides.items():
            target_aliases = {
                normalize_alias(alias) for alias in genres[target_id].all_aliases
            }
            if normalize_alias(source) not in target_aliases:
                msg = (
                    f"manual override {source!r} is not declared by target "
                    f"{target_id}"
                )
                raise ValueError(msg)
        for source, tags in (
            ("lastfm", profile.lastfm_collection_tags),
            ("musicbrainz", profile.musicbrainz_collection_tags),
        ):
            declared = {
                normalize_alias(alias)
                for genre_id in profile.canonical_genre_ids
                for alias in (
                    genres[genre_id].lastfm_spelling_variants
                    if source == "lastfm"
                    else genres[genre_id].musicbrainz_spelling_variants
                )
            }
            undeclared = sorted(
                tag for tag in tags if normalize_alias(tag) not in declared
            )
            if undeclared:
                msg = f"{source} collection tags lack declared variants: {undeclared}"
                raise ValueError(msg)

    @property
    def genre_by_id(self) -> dict[str, GenreDefinition]:
        """Index definitions by stable ID."""
        return {genre.genre_id: genre for genre in self.genres}

    @property
    def canonical_genres(self) -> tuple[str, ...]:
        """Return the frozen Phase-B canonical labels used by current metrics."""
        genres = self.genre_by_id
        return tuple(
            genres[genre_id].canonical_name
            for genre_id in self.production_compatibility.canonical_genre_ids
        )

    @property
    def manual_overrides(self) -> dict[str, str]:
        """Return current resolver overrides without enabling v2 candidates."""
        genres = self.genre_by_id
        return {
            source: genres[target_id].canonical_name
            for source, target_id in self.production_compatibility.manual_overrides.items()
        }

    def collection_tags(self, source: SourceSystem) -> tuple[str, ...]:
        """Return the frozen collector view for one official source."""
        if source == "lastfm":
            return self.production_compatibility.lastfm_collection_tags
        return self.production_compatibility.musicbrainz_collection_tags

    def collection_tags_v2(self, source: SourceSystem) -> tuple[str, ...]:
        """Return deterministic source tags for enabled and candidate genres.

        Rejected definitions and the explicit ``other``/``unresolved`` states
        never drive collection. Equivalent source spellings are requested once
        globally, ignoring case.
        """

        special_ids = {self.other_genre_id, self.unresolved_genre_id}
        values = (
            (
                genre.lastfm_spelling_variants
                if source == "lastfm"
                else genre.musicbrainz_spelling_variants
            )
            for genre in self.genres
            if genre.status in {"enabled", "candidate"}
            and genre.genre_id not in special_ids
        )
        by_normalized: dict[str, str] = {}
        for variants in values:
            for variant in variants:
                by_normalized.setdefault(variant.casefold(), variant)
        return tuple(by_normalized[key] for key in sorted(by_normalized))

    def resolve_alias(
        self,
        value: str,
        *,
        macro_family_id: str | None = None,
    ) -> GenreDefinition:
        """Resolve an exact normalized alias or return explicit unresolved."""
        normalized = normalize_alias(value)
        matches = tuple(
            genre
            for genre in self.genres
            if genre.status != "rejected"
            and (
                macro_family_id is None
                or genre.macro_family_id == macro_family_id
            )
            and normalized
            in {normalize_alias(alias) for alias in genre.all_aliases}
        )
        if len(matches) == 1:
            return matches[0]
        return self.genre_by_id[self.unresolved_genre_id]

    def counts_by_macro_family_and_status(
        self,
    ) -> dict[str, dict[GenreStatus, int]]:
        """Return deterministic taxonomy inventory counts."""
        counts: Counter[tuple[str, GenreStatus]] = Counter(
            (genre.macro_family_id, genre.status) for genre in self.genres
        )
        return {
            family.macro_family_id: {
                status: counts[(family.macro_family_id, status)]
                for status in GENRE_STATUSES
            }
            for family in self.macro_families
        }


def _require_unique(values: Iterable[str], *, label: str) -> None:
    sequence = tuple(values)
    duplicates = sorted(
        value for value, count in Counter(sequence).items() if count > 1
    )
    if duplicates:
        msg = f"duplicate {label} values: {duplicates}"
        raise ValueError(msg)


def load_taxonomy(path: Path = DEFAULT_TAXONOMY_PATH) -> GenreTaxonomy:
    """Read and validate the shared taxonomy YAML at an I/O boundary."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GenreTaxonomy.model_validate(payload)
