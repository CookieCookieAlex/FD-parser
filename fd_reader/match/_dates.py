"""Date/time-parsing helpers shared across the match package's submodules."""
from __future__ import annotations

import re
from datetime import date, datetime


def parse_mmddyyyy(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def parse_source_date(text: str) -> date | None:
    """ReservationRecord.source_date is like 'Jun 20, 2026' (see
    parse_reservations.py's _find_date_from_filter_bar) -- but that
    extraction regex captures the month token generically (\\w+), so it
    would just as happily capture a full month name like 'June' if Yelp
    ever renders one; try both forms rather than silently failing every
    reservation in that day's file if it does."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue
    return None


_TIME_HOUR_MINUTE_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?")


def _time_hour_minute(time_text: str) -> tuple[int, int] | None:
    match = _TIME_HOUR_MINUTE_RE.search(time_text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    return hour, minute


def note_time_matches(note_time_text: str | None, reservation_time: str) -> bool:
    """True if a note's free-text time (e.g. "7PM", "6:30") names the same
    hour/minute as a ReservationRecord's clean "H:MM" time. A note with no
    parseable time (common -- see parsing/notes/dates.py's TIME_RE requiring an
    AM/PM marker) never matches; this is a secondary signal, not a
    requirement -- "no time in the note" just means it can't help here."""
    if not note_time_text:
        return False
    note_time = _time_hour_minute(note_time_text)
    reservation_time_parsed = _time_hour_minute(reservation_time)
    if note_time is None or reservation_time_parsed is None:
        return False
    return note_time == reservation_time_parsed
