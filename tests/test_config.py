"""Shared production views over taxonomy v2."""

from pathlib import Path

import yaml

from soundcheck.config import load_genres
from soundcheck.taxonomy import load_taxonomy

PRE_V2_VIEWS = Path("tests/fixtures/pre_v2_genre_views.yml")


def test_genres_span_mainstream_and_niche_without_duplicates() -> None:
    genres = load_genres().genres

    assert len(genres) >= 100
    assert len({genre.casefold() for genre in genres}) == len(genres)
    assert {
        "indie rock",
        "shoegaze",
        "hyperpop",
        "dungeon synth",
        "jungle",
        "breakcore",
        "ambient",
        "slowcore",
        "midwest emo",
        "dnb",
        "vaporwave",
        "post-punk",
        "bedroom pop",
        "math rock",
        "darkwave",
    }.issubset(genres)


def test_taxonomy_has_all_required_macro_families_and_frozen_views() -> None:
    taxonomy = load_taxonomy()
    family_ids = {family.macro_family_id for family in taxonomy.macro_families}

    assert taxonomy.taxonomy_version == "2.0.0"
    assert len(taxonomy.canonical_genres) == 63
    assert len(taxonomy.collection_tags("lastfm")) == 48
    assert taxonomy.collection_tags("lastfm") == taxonomy.collection_tags(
        "musicbrainz"
    )
    assert len(taxonomy.collection_tags_v2("lastfm")) >= 100
    assert len(taxonomy.collection_tags_v2("musicbrainz")) >= 100
    assert {
        "macro_african",
        "macro_asian_regional",
        "macro_caribbean",
        "macro_classical",
        "macro_electronic",
        "macro_experimental_ambient",
        "macro_folk_country",
        "macro_hip_hop",
        "macro_jazz",
        "macro_latin",
        "macro_metal",
        "macro_pop",
        "macro_punk",
        "macro_rnb_soul",
        "macro_rock",
    } <= family_ids
    assert taxonomy.resolve_alias("world music").genre_id == "genre_unresolved"


def test_phase_b_views_exactly_match_pre_v2_fixture() -> None:
    payload = yaml.safe_load(PRE_V2_VIEWS.read_text(encoding="utf-8"))
    taxonomy = load_taxonomy()

    assert taxonomy.canonical_genres == tuple(payload["canonical_genres"])
    assert taxonomy.collection_tags("lastfm") == tuple(payload["collector_tags"])
    assert taxonomy.collection_tags("musicbrainz") == tuple(
        payload["collector_tags"]
    )
