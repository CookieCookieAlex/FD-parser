"""Extract restaurant reservation mentions out of a guest's free-text note
fields (`guest_notes`, `reservation_notes`, `comments_notes` on
GuestRecord) -- this is the staff's existing manual cross-reference to a
Yelp reservation, and per CLAUDE.md's matching strategy this needs to be
checked against what's actually in the Yelp data (a mention with no
matching Yelp reservation, or a Yelp reservation with no corresponding
note, are both worth flagging).

Two distinct note styles show up in the real sample data (see
SESSION_HISTORY.md/CLAUDE.md) written by different staff members:

  - Explicit-date notes (mixed case), e.g. "Maggie's 6/30 @ 7PM",
    "Artisans 6/29 @ 7PM, Maggie's 7/1 @ 6:30", "7/3 & 7/4-maggies @ 7pm
    2ppl", "Artisans on 06/25 & 26 @ 7PM" (a same-month two-day range),
    "June 26th-Thursday- Artisans @ 8Pm 4 ppl" (spelled month+day AND a
    weekday together -- the weekday here is redundant/self-checking, not
    needed to resolve the date, but is cross-checked against the
    explicit date as a sanity check).
  - Weekday-only notes, ALL CAPS, written by one specific staff member who
    never includes a date -- e.g. "TUESDAY MAGGIES 6PM, WEDNESDAY ARTISANS
    6PM", "THURSDAY ARTISANS 7:00PM, SUNDAY MAGGIES 6:00PM", "FRIDAY
    ARTISANS 7PM, SATURDAY MAGGIES 7PM, SATURDAY ARTISANS 7PM". These have
    no date at all -- the day name must be resolved to an actual date by
    finding which date in the guest's [arrival_date, departure_date) stay
    window falls on that weekday.

A stay window can contain the same weekday twice (any stay of 7+ nights),
in which case the weekday cannot be resolved to a single date -- flagged
as ambiguous rather than guessed, consistent with the project-wide "flag,
don't guess" rule (see CLAUDE.md's matching strategy step 5).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

RESTAURANT_KEYWORDS = {
    "artisan": "Artisans",   # covers "artisans"/"Artison" typo family too loosely on purpose;
    "maggie": "Maggie's",    # exact keyword set intentionally mirrors parse_reservations.py
}

_WEEKDAYS = [
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
]
_WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)

# M/D or MM/DD, optionally with a leading "on ", and optionally followed by
# a second day joined with "&" -- either a bare day ("06/25 & 26") or a
# full second M/D ("7/3 & 7/4"). The bare-day alternative is tried first
# so "& 7/4" isn't mis-captured as "& 7" (a partial match on the second
# date's month).
_EXPLICIT_DATE_RE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})(?:\s*&\s*(?:\d{1,2}/)?(\d{1,2}))?\b"
)

# "June 26th" / "Jun 26" style -- seen once in real data ("June 26th-Thursday-").
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
_SPELLED_DATE_RE = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])\b")

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


def _parse_stay_date(mmddyyyy: str) -> date | None:
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", mmddyyyy.strip())
    if not match:
        return None
    month, day, year = (int(x) for x in match.groups())
    return date(year, month, day)


def _dates_in_stay(arrival: date, departure: date) -> list[date]:
    days = []
    cur = arrival
    while cur < departure:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _resolve_weekday(
    weekday_name: str, arrival: date, departure: date
) -> tuple[date | None, bool, list[date]]:
    """Returns (resolved_date_or_None, is_ambiguous, candidate_dates).
    Ambiguous means the weekday occurs more than once in
    [arrival, departure) -- candidate_dates then holds every occurrence,
    for match.py to narrow down using the guest's actual Yelp
    reservation(s)."""
    target = _WEEKDAYS.index(weekday_name.upper())
    matches = [d for d in _dates_in_stay(arrival, departure) if d.weekday() == target]
    if len(matches) == 1:
        return matches[0], False, []
    if len(matches) > 1:
        return None, True, matches
    return None, False, []


def _nearest_year_for_month_day(month: int, day: int, arrival: date, departure: date) -> date | None:
    """A spelled or numeric month/day has no year in the note text -- infer
    it from whichever of the stay's arrival/departure years produces a
    date inside (or nearest to) the stay window, since a stay can span a
    New Year's Eve boundary."""
    for year in (arrival.year, departure.year):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if arrival <= candidate <= departure:
            return candidate
    try:
        return date(arrival.year, month, day)
    except ValueError:
        return None


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

    arrival_date = _parse_stay_date(arrival)
    departure_date = _parse_stay_date(departure)

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

        time_match = _TIME_RE.search(entry)
        time_text = time_match.group(0) if time_match else None

        weekday_match = _WEEKDAY_RE.search(entry)
        explicit_match = _EXPLICIT_DATE_RE.search(entry)
        spelled_match = _SPELLED_DATE_RE.search(entry)
        weekday_text = weekday_match.group(1).upper() if weekday_match else None

        resolved_dates: list[date] = []
        is_ambiguous = False
        candidate_dates: list[date] = []
        flags: list[str] = []

        if arrival_date is None or departure_date is None:
            flags.append("unparseable_stay_dates")
        elif explicit_match:
            month, day = int(explicit_match.group(1)), int(explicit_match.group(2))
            first = _nearest_year_for_month_day(month, day, arrival_date, departure_date)
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
            month = _MONTH_NAMES[spelled_match.group(1).lower()]
            day = int(spelled_match.group(2))
            first = _nearest_year_for_month_day(month, day, arrival_date, departure_date)
            if first is not None:
                resolved_dates.append(first)
            else:
                flags.append("date_outside_stay_window")
        elif weekday_match:
            resolved, is_ambiguous, candidate_dates = _resolve_weekday(
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
