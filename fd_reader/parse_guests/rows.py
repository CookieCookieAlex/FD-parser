"""Row/word extraction and row-classification helpers for the guest-arrivals
PDF. See the package docstring (fd_reader/parse_guests/__init__.py) for the
overall parsing strategy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
CONFIRMATION_RE = re.compile(r"^\d+-\d+$")

# Row grouping tolerance: words on the same printed line can differ in
# `top` by a point or two due to font metrics.
ROW_TOP_TOLERANCE = 2.0

# x0 boundary between the right-aligned label column and its value column
# (see CLAUDE.md: labels end ~158, values start ~163).
LABEL_VALUE_BOUNDARY = 160.0


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Row:
    words: list[Word]
    top: float

    def text_in_range(self, x0: float | None = None, x1: float | None = None) -> str:
        selected = [
            w
            for w in self.words
            if (x0 is None or w.x0 >= x0) and (x1 is None or w.x0 < x1)
        ]
        return " ".join(w.text for w in selected)


def extract_rows(page) -> list[Row]:
    words = [
        Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
        for w in page.extract_words(use_text_flow=False, keep_blank_chars=False)
    ]
    words.sort(key=lambda w: (w.top, w.x0))

    rows: list[Row] = []
    for w in words:
        if rows and abs(w.top - rows[-1].top) <= ROW_TOP_TOLERANCE:
            rows[-1].words.append(w)
        else:
            rows.append(Row(words=[w], top=w.top))
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


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
        if 235 <= w.x0 <= 330 and w.text not in ("", None):
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
    arrival = find_date_word(row, 325, 430)
    if status and arrival:
        return status, arrival
    return None
