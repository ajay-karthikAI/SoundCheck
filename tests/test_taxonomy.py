"""Fixture-based taxonomy v2 validation and resolution tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from soundcheck.taxonomy import (
    GenreTaxonomy,
    load_taxonomy,
    normalize_alias,
)

FIXTURE_PATH = Path("tests/fixtures/taxonomy_v2.yml")


@pytest.fixture
def taxonomy_payload() -> dict[str, Any]:
    payload = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _genre(payload: dict[str, Any], genre_id: str) -> dict[str, Any]:
    genres = payload["genres"]
    assert isinstance(genres, list)
    return next(item for item in genres if item["genre_id"] == genre_id)


def test_aliases_and_multilingual_normalization_are_deterministic() -> None:
    taxonomy = load_taxonomy(FIXTURE_PATH)

    assert normalize_alias("  MÚSICA—ROCK ") == "musica rock"
    assert taxonomy.resolve_alias("musica rock").genre_id == "genre_rock"
    assert (
        taxonomy.resolve_alias("ガレージロック").genre_id
        == "genre_garage_rock"
    )
    assert tuple(genre.genre_id for genre in taxonomy.genres) == tuple(
        sorted(genre.genre_id for genre in taxonomy.genres)
    )


def test_cross_family_ambiguity_and_unknown_values_remain_unresolved() -> None:
    taxonomy = load_taxonomy(FIXTURE_PATH)

    assert taxonomy.resolve_alias("garage").genre_id == "genre_unresolved"
    assert (
        taxonomy.resolve_alias(
            "garage",
            macro_family_id="macro_rock",
        ).genre_id
        == "genre_garage_rock"
    )
    assert taxonomy.resolve_alias("not a real genre").genre_id == "genre_unresolved"
    assert taxonomy.resolve_alias("").genre_id == "genre_unresolved"


def test_duplicate_genre_ids_are_rejected(
    taxonomy_payload: dict[str, Any],
) -> None:
    payload = deepcopy(taxonomy_payload)
    genres = payload["genres"]
    genres.append(deepcopy(genres[0]))

    with pytest.raises(ValidationError, match="duplicate genre_id"):
        GenreTaxonomy.model_validate(payload)


def test_duplicate_slugs_are_rejected(
    taxonomy_payload: dict[str, Any],
) -> None:
    payload = deepcopy(taxonomy_payload)
    _genre(payload, "genre_garage_rock")["slug"] = "rock"

    with pytest.raises(ValidationError, match="duplicate genre slug"):
        GenreTaxonomy.model_validate(payload)


def test_invalid_parent_is_rejected(taxonomy_payload: dict[str, Any]) -> None:
    payload = deepcopy(taxonomy_payload)
    _genre(payload, "genre_garage_rock")["parent_genre_id"] = "genre_missing"

    with pytest.raises(ValidationError, match="unknown parent_genre_id"):
        GenreTaxonomy.model_validate(payload)


def test_hierarchy_cycle_is_rejected(taxonomy_payload: dict[str, Any]) -> None:
    payload = deepcopy(taxonomy_payload)
    _genre(payload, "genre_rock")["parent_genre_id"] = "genre_garage_rock"

    with pytest.raises(ValidationError, match="hierarchy contains a cycle"):
        GenreTaxonomy.model_validate(payload)


def test_duplicate_normalized_alias_within_family_is_rejected(
    taxonomy_payload: dict[str, Any],
) -> None:
    payload = deepcopy(taxonomy_payload)
    _genre(payload, "genre_rock")["aliases"] = ["GARAGE"]

    with pytest.raises(ValidationError, match="multiple genres"):
        GenreTaxonomy.model_validate(payload)


def test_invalid_taxonomy_version_is_rejected(
    taxonomy_payload: dict[str, Any],
) -> None:
    payload = deepcopy(taxonomy_payload)
    payload["taxonomy_version"] = "v2"

    with pytest.raises(ValidationError, match="major version 2"):
        GenreTaxonomy.model_validate(payload)


def test_genre_version_must_match_root(
    taxonomy_payload: dict[str, Any],
) -> None:
    payload = deepcopy(taxonomy_payload)
    _genre(payload, "genre_rock")["taxonomy_version"] = "2.1.0"

    with pytest.raises(ValidationError, match="must match the root version"):
        GenreTaxonomy.model_validate(payload)
