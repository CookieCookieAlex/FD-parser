"""Word/row extraction and boilerplate filtering for the Yelp reservations
PDF -- the same word-coordinate -> row grouping approach as
parsing/guests/rows.py, tuned to Yelp's column bands and page furniture
(page title, footer, filter bar) instead of the arrivals report's.

See CLAUDE.md's "Yelp for Business reservations PDF" section for the exact
pixel layout this was reverse-engineered from.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
PHONE_RE = re.compile(r"^\(\d{3}\)$")

# x0 column bands, confirmed against real sample PDFs.
COL_TIME = (40, 95)
COL_PARTY = (100, 145)
COL_GUEST = (170, 270)
COL_NOTES = (275, 355)

ROW_TOP_TOLERANCE = 2.0


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

    def text_in(self, band: tuple[float, float]) -> str:
        selected = [w for w in self.words if band[0] <= w.x0 < band[1]]
        return " ".join(w.text for w in selected)

    def words_in(self, band: tuple[float, float]) -> list[Word]:
        return [w for w in self.words if band[0] <= w.x0 < band[1]]


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


def find_date_from_filter_bar(rows: list[Row]) -> str | None:
    for row in rows:
        text = row.text_in((60, 350))
        match = re.search(
            r"(?:Today|Future Day|Yesterday)\s+\w+,\s+(\w+ \d{1,2}, \d{4})", text
        )
        if match:
            return match.group(1)
    return None


# The page footer ("About / Discover / Languages / Get the Yelp for
# Business app / Content Guidelines / Accessibility Statement / Terms of
# Service / Privacy Policy / Need Help? / Copyright (C) Yelp Inc. / the
# biz.yelp.com URL" etc) sits at a `top` that varies by how many
# reservation rows are on the page, so it can't be filtered by position
# alone -- match on its known fixed phrases instead. Checked one at a time
# (not a full-row match) since a stray phrase can share a row with real
# footer text but not with reservation data.
_FOOTER_PHRASES = (
    "About", "Discover", "Languages", "Get the Yelp for Business app",
    "Content Guidelines", "Accessibility Statement", "Business Resource Center",
    "Terms of Service", "Yelp Business Blog", "Privacy Policy",
    "Yelp for Restaurants", "Carrier rates may apply", "Ad Choices",
    "Trust & Safety", "Manage Cookies", "Support", "Copyright", "Yelp Inc.",
    "Need Help?", "Send link", "Enter your number", "download the app",
    "biz.yelp.com",
)


def is_boilerplate(row: Row) -> bool:
    text = row.text_in((0, 600))
    if not text.strip():
        return True
    # Page title ("6/28/26, 12:17 PM  Artisans at the Lake Placid Lodge |
    # Yelp for Business") and the "... for business" tagline repeat at the
    # same low `top` on every single page -- including continuation pages
    # -- and the page-title timestamp otherwise looks exactly like a
    # reservation Time-column value, so it must be excluded by position,
    # not by text match.
    if row.top < 60:
        return True
    if text.startswith("Time Party") or "Guest Details" in text:
        return True
    if text.startswith("Notes & Tags") or text.strip() == "Tags":
        return True
    if re.match(r"^(Today|Future Day|Yesterday)\b", text):
        return True
    if text.startswith("Total Covers") or "Total Covers" in text:
        return True
    if any(phrase in text for phrase in _FOOTER_PHRASES):
        return True
    return False


def footer_start_top(rows: list[Row]) -> float | None:
    """The page footer is a fixed block of rows (About/Discover/Languages/
    Content Guidelines/.../Copyright/the biz.yelp.com URL) whose `top`
    varies with how many reservations are on the page -- but once it
    starts, EVERYTHING after it on the page is footer, including a lone
    'English' row (the Languages column's value) that would otherwise look
    like a continuation line of the last reservation's Notes & Tags."""
    for row in rows:
        text = row.text_in((0, 600))
        if any(phrase in text for phrase in _FOOTER_PHRASES):
            return row.top
    return None


def is_reservation_start_row(row: Row) -> bool:
    time_words = row.words_in(COL_TIME)
    return any(TIME_RE.match(w.text) for w in time_words)


def parse_party_size(row: Row) -> int | None:
    for w in row.words_in(COL_PARTY):
        if w.text.isdigit():
            return int(w.text)
    return None
