"""Shared file fixtures for the offline test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def fixtures_path() -> Path:
    """Return the immutable fixture directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def classification_cases(fixtures_path: Path) -> list[dict[str, Any]]:
    """Load classification cases from disk."""
    value: object = json.loads(
        (fixtures_path / "classification_cases.json").read_text(encoding="utf-8")
    )
    assert isinstance(value, list)
    return value


@pytest.fixture
def jetstream_message(fixtures_path: Path) -> bytes:
    """Load one raw Jetstream message."""
    return (fixtures_path / "jetstream_music_post.json").read_bytes()


@pytest.fixture
def appview_payload(fixtures_path: Path) -> dict[str, Any]:
    """Load a representative public AppView payload."""
    value: object = json.loads((fixtures_path / "appview_posts.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def lastfm_responses(fixtures_path: Path) -> dict[str, Any]:
    """Load official-shape Last.fm response fixtures."""
    value: object = json.loads(
        (fixtures_path / "lastfm_responses.json").read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


@pytest.fixture
def musicbrainz_pages(fixtures_path: Path) -> dict[str, Any]:
    """Load paginated MusicBrainz response fixtures."""
    value: object = json.loads(
        (fixtures_path / "musicbrainz_pages.json").read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value
