"""Pure music classifier tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from soundcheck.ingest.bluesky.classify import is_music_post


def test_fixture_cases_include_adversarial_false_positives(
    classification_cases: list[dict[str, Any]],
) -> None:
    for case in classification_cases:
        post = case["post"]
        original = deepcopy(post)

        result = is_music_post(post)

        assert list(result.rules) == case["rules"], case["id"]
        assert post == original


@pytest.mark.parametrize(
    ("url", "rule"),
    [
        ("https://artist.bandcamp.com/track/one", "link:bandcamp.com"),
        ("https://soundcloud.com/artist/one", "link:soundcloud.com"),
        ("https://open.spotify.com/track/one", "link:open.spotify.com"),
        ("https://music.apple.com/us/album/one", "link:music.apple.com"),
        ("https://www.youtube.com/watch?v=one", "link:youtube.com"),
        ("https://youtu.be/one", "link:youtu.be"),
        ("https://www.last.fm/music/artist", "link:last.fm"),
    ],
)
def test_all_official_link_facet_rules(url: str, rule: str) -> None:
    post = {
        "text": "listen",
        "createdAt": "2026-07-20T12:00:00Z",
        "facets": [
            {
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url,
                    }
                ]
            }
        ],
    }

    result = is_music_post(post)

    assert result.rules == (rule,)
    assert result.link_urls == (url,)


@pytest.mark.parametrize(
    "url",
    [
        # Facet URIs observed on the public firehose that urlsplit rejects.
        "https://NHL.com]",
        "https://gihyo.jp](https://gihyo.jp/article/2026/09/cloudflare-worker-previews)",
        "https://ASCII.jp\uff1anews",
    ],
)
def test_unparseable_link_facets_do_not_stop_classification(url: str) -> None:
    post = {
        "text": "#nowplaying",
        "createdAt": "2026-07-20T12:00:00Z",
        "facets": [
            {
                "features": [
                    {
                        "$type": "app.bsky.richtext.facet#link",
                        "uri": url,
                    }
                ]
            }
        ],
    }

    result = is_music_post(post)

    assert result.rules == ("hashtag:#nowplaying",)
    assert result.link_urls == (url,)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("#NOWPLAYING", "hashtag:#nowplaying"),
        ("#np", "hashtag:#np"),
        ("#NewMusic", "hashtag:#newmusic"),
        ("#newrelease", "hashtag:#newrelease"),
        ("Listening to this", "intent:listening_to"),
        ("On repeat all day", "intent:on_repeat"),
        ("A new album arrives", "intent:new_album"),
        ("Their new EP arrives", "intent:new_ep"),
        ("A new single by the band", "intent:new_single"),
        ("The mixtape just dropped", "intent:just_dropped"),
    ],
)
def test_hashtag_and_intent_rules(text: str, rule: str) -> None:
    result = is_music_post({"text": text, "createdAt": "2026-07-20T12:00:00Z"})

    assert rule in result.rules


def test_word_boundaries_do_not_match_substrings() -> None:
    result = is_music_post(
        {
            "text": "playlistening together; brand-new singletons",
            "createdAt": "2026-07-20T12:00:00Z",
        }
    )

    assert not result

