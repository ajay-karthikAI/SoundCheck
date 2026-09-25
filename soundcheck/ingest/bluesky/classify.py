"""Pure, conservative music-intent classification for Bluesky posts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from soundcheck.ingest.bluesky.models import FeedPost

_MUSIC_LINK_HOSTS = (
    "bandcamp.com",
    "soundcloud.com",
    "open.spotify.com",
    "music.apple.com",
    "youtube.com",
    "youtu.be",
    "last.fm",
)
_MUSIC_HASHTAGS = frozenset({"nowplaying", "np", "newmusic", "newrelease"})
_HASHTAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_]+)\b")
_NO_PROBLEM_RE = re.compile(
    r"\b(?:no\s+problem|happy\s+to\s+help|you(?:'re|\s+are)\s+welcome|anytime)\b",
    re.IGNORECASE,
)
_DATING_CONTEXT_RE = re.compile(
    r"\b(?:dating|relationship|tinder|bumble|hinge|boyfriend|girlfriend|"
    r"divorc(?:e|ed)|breakup|romantic|eligible bachelor)\b",
    re.IGNORECASE,
)
_PERSON_IS_NEW_SINGLE_RE = re.compile(
    r"\b(?:i(?:'m|\s+am)|he(?:'s|\s+is)|she(?:'s|\s+is)|they(?:'re|\s+are)|"
    r"newly|currently)\s+(?:a\s+)?new\s+single\b",
    re.IGNORECASE,
)
_SPORTS_DROP_RE = re.compile(
    r"\bjust\s+dropped\s+(?:the\s+)?(?:ball|pass|catch|punt|game|match)\b",
    re.IGNORECASE,
)
_INTENT_PATTERNS = (
    ("intent:listening_to", re.compile(r"\blistening\s+to\b", re.IGNORECASE)),
    ("intent:on_repeat", re.compile(r"\bon\s+repeat\b", re.IGNORECASE)),
    ("intent:new_album", re.compile(r"\bnew\s+album\b", re.IGNORECASE)),
    ("intent:new_ep", re.compile(r"\bnew\s+ep\b", re.IGNORECASE)),
    ("intent:new_single", re.compile(r"\bnew\s+single\b", re.IGNORECASE)),
    ("intent:just_dropped", re.compile(r"\bjust\s+dropped\b", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class Match:
    """Classification result, including evidence extracted from the post."""

    rules: tuple[str, ...]
    link_urls: tuple[str, ...]
    hashtags: tuple[str, ...]

    @property
    def matched(self) -> bool:
        """Whether at least one music rule matched."""
        return bool(self.rules)

    @property
    def matched_rules(self) -> tuple[str, ...]:
        """Alias matching the persisted column name."""
        return self.rules

    def __bool__(self) -> bool:
        return self.matched


def _deduplicate(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _feature_type(feature: Mapping[str, Any]) -> str:
    value = feature.get("$type")
    return value if isinstance(value, str) else ""


def _extract_links(post: FeedPost) -> tuple[str, ...]:
    links: list[str] = []
    for facet in post.facets:
        for feature in facet.features:
            if not _feature_type(feature).endswith("#link"):
                continue
            uri = feature.get("uri")
            if isinstance(uri, str):
                links.append(uri)
    return _deduplicate(links)


def _extract_hashtags(post: FeedPost) -> tuple[str, ...]:
    hashtags: list[str] = []
    for facet in post.facets:
        for feature in facet.features:
            if not _feature_type(feature).endswith("#tag"):
                continue
            tag = feature.get("tag")
            if isinstance(tag, str) and tag:
                hashtags.append(tag.removeprefix("#"))
    hashtags.extend(match.group(1) for match in _HASHTAG_RE.finditer(post.text))
    return _deduplicate(hashtags)


def _matching_link_host(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        # Facet URIs are client-supplied (e.g. "https://NHL.com]"); one that
        # urlsplit rejects cannot be a music link and must not stop ingestion.
        return None
    for allowed_host in _MUSIC_LINK_HOSTS:
        if host == allowed_host or host.endswith(f".{allowed_host}"):
            return allowed_host
    return None


def _hashtag_is_music(tag: str, text: str) -> bool:
    normalized = tag.casefold()
    if normalized not in _MUSIC_HASHTAGS:
        return False
    return not (normalized == "np" and _NO_PROBLEM_RE.search(text))


def _intent_is_false_positive(rule: str, text: str) -> bool:
    if rule == "intent:new_single":
        return bool(_DATING_CONTEXT_RE.search(text) or _PERSON_IS_NEW_SINGLE_RE.search(text))
    if rule == "intent:just_dropped":
        return bool(_SPORTS_DROP_RE.search(text))
    return False


def is_music_post(post: FeedPost | Mapping[str, Any]) -> Match:
    """Classify one post without network, disk, clock, or global-state access."""
    parsed = post if isinstance(post, FeedPost) else FeedPost.model_validate(post)
    links = _extract_links(parsed)
    hashtags = _extract_hashtags(parsed)
    rules: list[str] = []

    for url in links:
        host = _matching_link_host(url)
        if host is not None:
            rules.append(f"link:{host}")

    for tag in hashtags:
        if _hashtag_is_music(tag, parsed.text):
            rules.append(f"hashtag:#{tag.casefold()}")

    for rule, pattern in _INTENT_PATTERNS:
        if pattern.search(parsed.text) and not _intent_is_false_positive(rule, parsed.text):
            rules.append(rule)

    return Match(
        rules=_deduplicate(rules),
        link_urls=links,
        hashtags=hashtags,
    )
