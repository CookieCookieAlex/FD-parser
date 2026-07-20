"""Date-parsing helpers shared across the match package's submodules."""
from __future__ import annotations

from datetime import date, datetime


def parse_mmddyyyy(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def parse_source_date(text: str) -> date | None:
    """ReservationRecord.source_date is like 'Jun 20, 2026' (see
    parse_reservations.py's _find_date_from_filter_bar)."""
    try:
        return datetime.strptime(text.strip(), "%b %d, %Y").date()
    except (ValueError, AttributeError):
        return None
