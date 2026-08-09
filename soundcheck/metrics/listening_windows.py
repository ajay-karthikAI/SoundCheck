"""Shared Last.fm snapshot-window integrity rules.

Last.fm exposes cumulative counters.  A delta is weekly evidence only when it
connects the latest observations from consecutive ISO weeks.  Elapsed days are
reported for auditability but are never used to rescale a delta.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

ListeningWindowStatus = Literal[
    "valid_weekly",
    "first_observation",
    "incomplete_pair",
    "not_append_only",
    "invalid_order",
    "same_week_duplicate",
    "nonconsecutive_weeks",
    "counter_decrease",
]

LASTFM_WINDOW_DERIVATION_VERSION = "lastfm_weekly_v2"


def iso_week_start(value: datetime) -> date:
    """Return the Monday of ``value``'s ISO week."""

    day = value.date()
    return day - timedelta(days=day.weekday())


def interval_days(
    previous_fetched_at: datetime | None,
    fetched_at: datetime,
) -> float | None:
    """Return exact elapsed days without normalizing or synthesizing rates."""

    if previous_fetched_at is None:
        return None
    return (fetched_at - previous_fetched_at).total_seconds() / 86_400.0


def classify_listening_window(
    *,
    previous_fetched_at: datetime | None,
    fetched_at: datetime,
    previous_playcount: int | None,
    playcount: int,
    previous_listeners: int | None,
    listeners: int,
    observations_append_only: bool = True,
) -> ListeningWindowStatus:
    """Classify one latest-week snapshot and its latest prior-week snapshot."""

    previous_values = (
        previous_fetched_at,
        previous_playcount,
        previous_listeners,
    )
    if all(value is None for value in previous_values):
        return "first_observation"
    if any(value is None for value in previous_values):
        return "incomplete_pair"
    if not observations_append_only:
        return "not_append_only"
    assert previous_fetched_at is not None
    assert previous_playcount is not None
    assert previous_listeners is not None
    if fetched_at <= previous_fetched_at:
        return "invalid_order"
    previous_week = iso_week_start(previous_fetched_at)
    current_week = iso_week_start(fetched_at)
    if current_week == previous_week:
        return "same_week_duplicate"
    if current_week - previous_week != timedelta(weeks=1):
        return "nonconsecutive_weeks"
    if playcount < previous_playcount or listeners < previous_listeners:
        return "counter_decrease"
    return "valid_weekly"
