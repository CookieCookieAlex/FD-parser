"""Extract restaurant reservation mentions out of a guest's free-text note
fields (`guest_notes`, `reservation_notes`, `comments_notes`) -- the
staff's existing manual cross-reference to a Yelp reservation, which gets
checked against the actual Yelp data. See CLAUDE.md's "Two distinct
note-writing styles" note for the explicit-date vs. weekday-only formats
this parses and the ambiguous-weekday rule.

dates.py holds the date/weekday regex + resolution helpers; this module
is the entry-splitting + extraction driver.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from fd_reader.parsing.notes.dates import (
    EXPLICIT_DATE_RE,
    SPELLED_DATE_RE,
    TIME_RE,
    WEEKDAY_RE,
    month_number,
    nearest_year_for_month_day,
    parse_stay_date,
    resolve_weekday,
)
from fd_reader.restaurants import RESTAURANT_KEYWORDS

__all__ = ["NoteMention", "extract_note_mentions"]

_RESTAURANT_SPAN_RE = re.compile(
    r"(artisan\w*|maggie'?s?)", re.IGNORECASE
)


@dataclass
class NoteMention:
    restaurant: str
    resolved_date: "date | None"
    time_text: str | None
    source_field: str
    raw_text: str
    weekday_text: str | None = None
    is_ambiguous_weekday: bool = False
    flags: list[str] = field(default_factory=list)
    # When is_ambiguous_weekday is True, resolved_date is None but this
    # carries every date in the stay window that falls on the mentioned
    # weekday (e.g. both Fridays of a 12-night stay) -- match.py can
    # narrow this down to one by checking which candidate date actually
    # has a matching Yelp reservation for this guest/restaurant. Empty for
    # non-ambiguous mentions.
    candidate_dates: list["date"] = field(default_factory=list)


def _split_entries(text: str) -> list[str]:
    """A single note field can list several mentions, comma-separated
    ("TUESDAY MAGGIES 6PM, WEDNESDAY ARTISANS 6PM") or blank-line
    separated (see CLAUDE.md's Comments/Notes multi-entry behavior).
    Split on both, but only where a restaurant keyword starts a new
    segment, so we don't fracture "7:00PM, SUNDAY MAGGIES" mid-mention."""
    segments = re.split(r"\n\n+", text)
    entries: list[str] = []
    for segment in segments:
        pieces = re.split(r",(?=\s*[A-Za-z0-9/])", segment)
        buf = ""
        for piece in pieces:
            if _RESTAURANT_SPAN_RE.search(piece) and buf:
                entries.append(buf.strip())
                buf = piece
            else:
                buf = f"{buf},{piece}" if buf else piece
        if buf.strip():
            entries.append(buf.strip())
    return entries


def extract_note_mentions(
    text: str, source_field: str, arrival: str, departure: str
) -> list[NoteMention]:
    """Scan one note field's raw text for restaurant reservation mentions.

    `arrival`/`departure` are the GuestRecord's raw MM/DD/YYYY strings
    (the [arrival, departure) window used to resolve weekday-only
    mentions to an actual date).
    """
    if not text or not text.strip():
        return []

    arrival_date = parse_stay_date(arrival)
    departure_date = parse_stay_date(departure)

    mentions: list[NoteMention] = []
    for entry in _split_entries(text):
        restaurant_match = _RESTAURANT_SPAN_RE.search(entry)
        if not restaurant_match:
            continue
        lowered = entry.lower()
        restaurant = None
        for keyword, name in RESTAURANT_KEYWORDS.items():
            if keyword in lowered:
                restaurant = name
                break
        if restaurant is None:
            continue

        time_match = TIME_RE.search(entry)
        time_text = time_match.group(0) if time_match else None

        weekday_match = WEEKDAY_RE.search(entry)
        explicit_match = EXPLICIT_DATE_RE.search(entry)
        spelled_match = SPELLED_DATE_RE.search(entry)
        weekday_text = weekday_match.group(1).upper() if weekday_match else None

        resolved_dates: list[date] = []
        is_ambiguous = False
        candidate_dates: list[date] = []
        flags: list[str] = []

        if arrival_date is None or departure_date is None:
            flags.append("unparseable_stay_dates")
        elif explicit_match:
            month, day = int(explicit_match.group(1)), int(explicit_match.group(2))
            first = nearest_year_for_month_day(month, day, arrival_date, departure_date)
            if first is not None:
                resolved_dates.append(first)
            # "06/25 & 26" -- a same-month two-day range, two separate
            # reservations sharing one note line, not one mention with a
            # typo. Second day reuses the first date's resolved month/year.
            second_day_group = explicit_match.group(3)
            if second_day_group is not None and first is not None:
                second_day = int(second_day_group)
                try:
                    resolved_dates.append(date(first.year, first.month, second_day))
                except ValueError:
                    pass
            if not resolved_dates:
                flags.append("date_outside_stay_window")
        elif spelled_match:
            month = month_number(spelled_match.group(1))
            day = int(spelled_match.group(2))
            first = nearest_year_for_month_day(month, day, arrival_date, departure_date)
            if first is not None:
                resolved_dates.append(first)
            else:
                flags.append("date_outside_stay_window")
        elif weekday_match:
            resolved, is_ambiguous, candidate_dates = resolve_weekday(
                weekday_match.group(1), arrival_date, departure_date
            )
            if resolved is not None:
                resolved_dates.append(resolved)
            if is_ambiguous:
                flags.append("ambiguous_weekday")
        else:
            flags.append("no_date_found_in_note")

        if not resolved_dates:
            mentions.append(
                NoteMention(
                    restaurant=restaurant,
                    resolved_date=None,
                    time_text=time_text,
                    source_field=source_field,
                    raw_text=entry.strip(),
                    weekday_text=weekday_text,
                    is_ambiguous_weekday=is_ambiguous,
                    flags=flags,
                    candidate_dates=candidate_dates,
                )
            )
        else:
            for resolved_date in resolved_dates:
                mentions.append(
                    NoteMention(
                        restaurant=restaurant,
                        resolved_date=resolved_date,
                        time_text=time_text,
                        source_field=source_field,
                        raw_text=entry.strip(),
                        weekday_text=weekday_text,
                        is_ambiguous_weekday=is_ambiguous,
                        flags=list(flags),
                    )
                )

    return mentions
