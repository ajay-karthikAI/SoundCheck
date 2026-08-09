"""Closed MusicBrainz first-release-date window planning."""

from datetime import date, timedelta


def latest_closed_iso_week_end(as_of: date) -> date:
    """Return the Sunday ending the latest fully closed ISO week."""

    current_week_start = as_of - timedelta(days=as_of.weekday())
    return current_week_start - timedelta(days=1)


def incremental_window(as_of: date, *, days: int = 14) -> tuple[date, date]:
    """Return a bounded trailing window ending on a closed ISO-week Sunday."""

    if days <= 0:
        raise ValueError("days must be positive")
    end_date = latest_closed_iso_week_end(as_of)
    return end_date - timedelta(days=days - 1), end_date
