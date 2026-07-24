"""Row/word extraction and row-classification helpers for the guest-arrivals
PDF. See the package docstring (fd_reader/parsing/guests/__init__.py) for the
overall parsing strategy. Word/Row/extract_rows live in parsing/_pdf_rows.py,
shared with parsing/reservations/rows.py.
"""
from __future__ import annotations

import re

from fd_reader.parsing._pdf_rows import Row, Word, extract_rows

__all__ = [
    "Row", "Word", "extract_rows",
    "is_boilerplate", "find_status_word", "find_date_word",
    "is_stay_date_row", "is_record_anchor",
    "DATE_RE", "LABEL_VALUE_BOUNDARY",
    "COL_ROOM", "COL_NAME_OR_CONFIRMATION", "COL_STATUS",
    "COL_ARRIVAL_OR_DEPARTURE", "COL_GUESTS_SHARE", "COL_RATE_PLAN",
]

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

# x0 boundary between the right-aligned label column and its value column
# (see CLAUDE.md: labels end ~158, values start ~163).
LABEL_VALUE_BOUNDARY = 160.0

# x0 column bands on the anchor/detail rows, confirmed against real sample
# PDFs. Room name (anchor row) and room type (detail row) share a column,
# as do guest name (anchor row) and confirmation number (detail row) --
# same x0 range, different row.
COL_ROOM = (0, 100)
COL_NAME_OR_CONFIRMATION = (100, 235)
COL_STATUS = (235, 330)
COL_ARRIVAL_OR_DEPARTURE = (325, 430)
COL_GUESTS_SHARE = (435, 460)
COL_RATE_PLAN = (490, 574)


def is_boilerplate(row: Row) -> bool:
    text = row.text_in_range()
    if text.startswith("Arrivals with Details"):
        return True
    if text.startswith("Between") and "and" in text:
        return True
    if text.startswith("PROPERTY:"):
        return True
    if text.startswith("USER:"):
        return True
    if text.startswith("Room Guest Name") or text.startswith("Room Type Confirmation"):
        return True
    if re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2} Opal Collection", text):
        return True
    if text.startswith("Total Reservations") or "Total Reservations" in text:
        return True
    if text.startswith("Stay Date (Days)") or text.startswith("Room Type Rate Plan Rate"):
        return True
    return False


def find_status_word(row: Row) -> str | None:
    for w in row.words:
        if COL_STATUS[0] <= w.x0 <= COL_STATUS[1] and w.text not in ("", None):
            return w.text
    return None


def find_date_word(row: Row, x0_min: float, x0_max: float) -> str | None:
    for w in row.words:
        if x0_min <= w.x0 <= x0_max and DATE_RE.match(w.text):
            return w.text
    return None


def is_stay_date_row(row: Row) -> bool:
    text = row.text_in_range(x0=None, x1=LABEL_VALUE_BOUNDARY)
    return "Stay" in text and "Date" in text


def is_record_anchor(row: Row) -> tuple[str, str] | None:
    """Return (status, arrival_date) if this row starts a new guest record."""
    status = find_status_word(row)
    arrival = find_date_word(row, *COL_ARRIVAL_OR_DEPARTURE)
    if status and arrival:
        return status, arrival
    return None
