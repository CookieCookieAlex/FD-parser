"""Date/weekday resolution for a note mention against a guest's stay
window -- the regexes for explicit (M/D), spelled ("June 26th"), and
weekday-only ("TUESDAY") date styles, plus the logic to turn a weekday
name into an actual date (or flag it ambiguous) within [arrival, departure).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

_WEEKDAYS = [
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
]
WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)

# M/D or MM/DD, optionally with a leading "on ", and optionally followed by
# a second day joined with "&" -- either a bare day ("06/25 & 26") or a
# full second M/D ("7/3 & 7/4"). The bare-day alternative is tried first
# so "& 7/4" isn't mis-captured as "& 7" (a partial match on the second
# date's month).
EXPLICIT_DATE_RE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})(?:\s*&\s*(?:\d{1,2}/)?(\d{1,2}))?\b"
)

# "June 26th" / "Jun 26" style -- seen once in real data ("June 26th-Thursday-").
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
SPELLED_DATE_RE = re.compile(
    r"\b(" + "|".join(_MONTH_NAMES) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])\b")


def month_number(month_name: str) -> int:
    return _MONTH_NAMES[month_name.lower()]


def parse_stay_date(mmddyyyy: str) -> date | None:
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", mmddyyyy.strip())
    if not match:
        return None
    month, day, year = (int(x) for x in match.groups())
    return date(year, month, day)


def dates_in_stay(arrival: date, departure: date) -> list[date]:
    days = []
    cur = arrival
    while cur < departure:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def resolve_weekday(
    weekday_name: str, arrival: date, departure: date
) -> tuple[date | None, bool, list[date]]:
    """Returns (resolved_date_or_None, is_ambiguous, candidate_dates).
    Ambiguous means the weekday occurs more than once in
    [arrival, departure) -- candidate_dates then holds every occurrence,
    for match.py to narrow down using the guest's actual Yelp
    reservation(s)."""
    target = _WEEKDAYS.index(weekday_name.upper())
    matches = [d for d in dates_in_stay(arrival, departure) if d.weekday() == target]
    if len(matches) == 1:
        return matches[0], False, []
    if len(matches) > 1:
        return None, True, matches
    return None, False, []


def nearest_year_for_month_day(month: int, day: int, arrival: date, departure: date) -> date | None:
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
