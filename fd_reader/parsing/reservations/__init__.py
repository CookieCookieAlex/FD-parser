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

rows.py holds word/row extraction + boilerplate/footer filtering;
fields.py derives restaurant/outside-guest/room-code-hint from Notes &
Tags text; this module holds ReservationRecord and the parse driver.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pdfplumber

from fd_reader.parsing.reservations.fields import (
    OUTSIDE_GUEST_KEYWORDS,
    derive_restaurant as _derive_restaurant,
    extract_room_code_hint as _extract_room_code_hint,
    is_outside_guest as _is_outside_guest,
)
from fd_reader.parsing.reservations.rows import (
    COL_GUEST,
    COL_NOTES,
    COL_PARTY,
    COL_TIME,
    PHONE_RE,
    Row,
    TIME_RE,
    Word,
    extract_rows as _extract_rows,
    find_date_from_filter_bar as _find_date_from_filter_bar,
    footer_start_top as _footer_start_top,
    is_boilerplate as _is_boilerplate,
    is_reservation_start_row as _is_reservation_start_row,
    parse_party_size as _parse_party_size,
)

__all__ = ["ReservationRecord", "parse_reservation_pdf", "Row", "Word", "PHONE_RE"]


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
