"""Parser for the Yelp for Business reservations PDF (biz.yelp.com print).

This is a printed browser page, not a native export -- includes browser nav
icons, footer, "Get the app" widget etc, which we ignore. Each PDF covers
ONE single day. See CLAUDE.md for the full structure notes; the big one:
the filename/page title does NOT reliably say which restaurant a row
belongs to (a file titled "Artisans..." can be full of Maggie's rows) --
restaurant identity must come from the `Notes & Tags` text per row.

Only what's actually needed downstream is extracted:
  - source_date: the single day this PDF covers (from the filter bar, e.g.
    "Today Sat, Jun 20, 2026" / "Future Day Thu, Jul 2, 2026") -- used to
    scope matching against the guest list's [arrival, departure) range.
  - per reservation: time, party size, guest name, phone, and the raw
    Notes & Tags text (from which restaurant + a room-code hint are
    derived). Everything else on the page (Total Covers/Reservations/
    Confirmed/Booked/Online/In House summary, Status, Seating Area, Table)
    is not needed and intentionally not parsed.

Layout (confirmed via scripts/dump_words.py against real sample PDFs):
  - Page title row (top~16-24): "<M/D/YY, h:mm AM/PM>  <restaurant name>
    Yelp for Business" -- NOT used for restaurant identity, only text noise.
  - Filter bar (top~359-366 on page 1 only): "Today Sat, Jun 20, 2026" or
    "Future Day Thu, Jul 2, 2026" -- this is the reservation date for the
    whole file.
  - One row per reservation, first line at x0 bands: Time x0~55, Party Size
    x0~104, Guest name x0~174, Notes&Tags x0~280. The row's SECOND line
    (x0~174) holds the guest's phone number when present. Notes&Tags can
    continue for several more lines (x0~280) after that -- it just keeps
    stacking lines for the same reservation until the next Time-column row
    starts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
PHONE_RE = re.compile(r"^\(\d{3}\)$")

# x0 column bands, confirmed against real sample PDFs.
COL_TIME = (40, 95)
COL_PARTY = (100, 145)
COL_GUEST = (170, 270)
COL_NOTES = (275, 355)

RESTAURANT_KEYWORDS = {
    "artisan": "Artisans",
    "maggie": "Maggie's",
}

# Seen in Notes & Tags for reservations that aren't tied to any in-house
# guest at all (e.g. "Guest R -- artisans off property no allergies").
OUTSIDE_GUEST_KEYWORDS = ("off property", "og", "outside guest")


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


@dataclass
class ReservationRecord:
    source_date: str
    time: str
    party_size: int | None
    guest_name: str
    phone: str
    notes_tags: str
    source_page: int
    restaurant: str | None = None
    room_code_hint: str | None = None
    is_outside_guest: bool = False
    flags: list[str] = field(default_factory=list)


ROW_TOP_TOLERANCE = 2.0


def _extract_rows(page) -> list[Row]:
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


def _find_date_from_filter_bar(rows: list[Row]) -> str | None:
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


def _is_boilerplate(row: Row) -> bool:
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


def _footer_start_top(rows: list[Row]) -> float | None:
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


def _is_reservation_start_row(row: Row) -> bool:
    time_words = row.words_in(COL_TIME)
    return any(TIME_RE.match(w.text) for w in time_words)


def _parse_party_size(row: Row) -> int | None:
    for w in row.words_in(COL_PARTY):
        if w.text.isdigit():
            return int(w.text)
    return None


def _derive_restaurant(notes_tags: str) -> str | None:
    lowered = notes_tags.lower()
    for keyword, restaurant in RESTAURANT_KEYWORDS.items():
        if keyword in lowered:
            return restaurant
    return None


def _is_outside_guest(notes_tags: str) -> bool:
    lowered = notes_tags.lower()
    return any(keyword in lowered for keyword in OUTSIDE_GUEST_KEYWORDS)


# Short internal shorthand seen in Notes & Tags (GH, hg, LM, EK, sz) --
# meaning isn't fully known and isn't needed for matching; stripped out of
# the room-code hint but not decoded.
_SHORTHAND_TOKENS = {"gh", "hg", "lm", "ek", "sz"}


def _extract_room_code_hint(notes_tags: str) -> str | None:
    text = notes_tags
    for keyword in RESTAURANT_KEYWORDS:
        text = re.sub(keyword, "", text, flags=re.IGNORECASE)
    for keyword in OUTSIDE_GUEST_KEYWORDS:
        text = re.sub(re.escape(keyword), "", text, flags=re.IGNORECASE)
    tokens = re.split(r"[\s,.\-]+", text)
    kept = [t for t in tokens if t and t.lower() not in _SHORTHAND_TOKENS]
    hint = " ".join(kept).strip(" -,.")
    return hint or None


def parse_reservation_pdf(path: str) -> list[ReservationRecord]:
    records: list[ReservationRecord] = []
    source_date: str | None = None

    with pdfplumber.open(path) as pdf:
        all_rows_by_page = []
        for page_index, page in enumerate(pdf.pages, start=1):
            rows = _extract_rows(page)
            all_rows_by_page.append((page_index, rows))
            if source_date is None:
                found = _find_date_from_filter_bar(rows)
                if found:
                    source_date = found

        current: ReservationRecord | None = None
        notes_lines: list[str] = []

        def finalize_current():
            nonlocal current, notes_lines
            if current is None:
                return
            notes_tags = " ".join(notes_lines).strip()
            current.notes_tags = notes_tags
            current.restaurant = _derive_restaurant(notes_tags)
            current.room_code_hint = _extract_room_code_hint(notes_tags)
            current.is_outside_guest = _is_outside_guest(notes_tags)
            if current.restaurant is None:
                current.flags.append("no_restaurant_detected")
            records.append(current)
            current = None
            notes_lines = []

        for page_index, rows in all_rows_by_page:
            footer_top = _footer_start_top(rows)
            for row in rows:
                if footer_top is not None and row.top >= footer_top:
                    continue
                if _is_boilerplate(row):
                    continue

                if _is_reservation_start_row(row):
                    finalize_current()
                    time_text = " ".join(w.text for w in row.words_in(COL_TIME))
                    current = ReservationRecord(
                        source_date=source_date or "",
                        time=time_text,
                        party_size=_parse_party_size(row),
                        guest_name=row.text_in(COL_GUEST).strip(),
                        phone="",
                        notes_tags="",
                        source_page=page_index,
                    )
                    notes_lines = []
                    first_notes = row.text_in(COL_NOTES).strip()
                    if first_notes:
                        notes_lines.append(first_notes)
                    continue

                if current is None:
                    continue

                guest_words = row.words_in(COL_GUEST)
                if guest_words and PHONE_RE.match(guest_words[0].text):
                    current.phone = " ".join(w.text for w in guest_words).strip()
                    notes_text = row.text_in(COL_NOTES).strip()
                    if notes_text:
                        notes_lines.append(notes_text)
                    continue

                notes_text = row.text_in(COL_NOTES).strip()
                if notes_text:
                    notes_lines.append(notes_text)

        finalize_current()

    return records
