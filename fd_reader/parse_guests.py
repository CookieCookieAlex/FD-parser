"""Parser for the guest-arrivals PDF ("Arrivals with Details").

This is not a table -- it's a label-anchored form, one variable-length block
per guest. See CLAUDE.md for the full structure notes. Strategy:

1. Extract words per page with pdfplumber, keep (x0, x1, top, bottom, text).
2. Group words into rows by `top` (words on the same printed line share a
   `top` within a small tolerance).
3. Drop boilerplate rows -- the repeated page header/footer/column-header
   text that appears on every page at (roughly) the same `top` bands.
4. Walk the remaining rows. A row is a new-record anchor when it has a
   `Reserved` (or other status word) in the status column and an
   MM/DD/YYYY date in the arrival-date column. Everything between one
   anchor and the next belongs to that guest's record.
5. Within a record: the row right after the anchor carries room type,
   confirmation number, and departure date. Subsequent rows are either
   `Stay Date (Days)` rows (skipped -- redundant with arrival/departure)
   or right-aligned label/value rows (`VIP Level:`, `Address:`,
   `Guest Notes:`, etc.) whose label sits in a narrow column ending
   around x1=158 and whose value starts around x0=163.
6. State (current record, current label being continued) carries across
   page boundaries, since notes can span a page break with no new anchor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

from fd_reader.models import GuestRecord

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
CONFIRMATION_RE = re.compile(r"^\d+-\d+$")

# Row grouping tolerance: words on the same printed line can differ in
# `top` by a point or two due to font metrics.
ROW_TOP_TOLERANCE = 2.0

# x0 boundary between the right-aligned label column and its value column
# (see CLAUDE.md: labels end ~158, values start ~163).
LABEL_VALUE_BOUNDARY = 160.0

# Known status words. Anything else is still treated as a valid anchor
# (so we don't silently drop rows) but is recorded as a parser warning.
KNOWN_STATUSES = {"Reserved"}

# Right-aligned labels that appear as "Label:" possibly split across
# multiple words (e.g. "Comments" "/" "Notes:"). Matched by joining the
# row's words in the label column and comparing against these strings.
LABEL_FIELD_MAP = {
    "VIP Level:": "vip_level",
    "Address:": "address",
    "Preferences:": "preferences",
    "Last Stay Property:": "last_stay_property",
    "Last Checkout Date:": "last_checkout_date",
    "Booking Agency:": "booking_agency",
    "Guest Notes:": "guest_notes",
    "Reservation Notes:": "reservation_notes",
    "Comments / Notes:": "comments_notes",
}

# Labels that share a row with other label/value pairs, e.g.
# "Last Stay Property: CODE   Lifetime Revenue: $x   Lifetime Stays: n   Lifetime Nights: n"
INLINE_LABELS = [
    "Lifetime Revenue:",
    "Lifetime Stays:",
    "Lifetime Nights:",
    "IATA:",
]
INLINE_LABEL_FIELD_MAP = {
    "Lifetime Revenue:": "lifetime_revenue",
    "Lifetime Stays:": "lifetime_stays",
    "Lifetime Nights:": "lifetime_nights",
    "IATA:": "iata",
}

# Multi-line free-text fields: once we've entered one of these, subsequent
# rows with no label of their own (i.e. rows that only have words right of
# LABEL_VALUE_BOUNDARY) are continuation lines of that field, until a new
# label row or new record anchor appears.
CONTINUATION_FIELDS = {"guest_notes", "reservation_notes", "comments_notes", "preferences", "address"}


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


def _is_boilerplate(row: Row) -> bool:
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


def _find_status_word(row: Row) -> str | None:
    for w in row.words:
        if 235 <= w.x0 <= 330 and w.text not in ("", None):
            return w.text
    return None


def _find_date_word(row: Row, x0_min: float, x0_max: float) -> str | None:
    for w in row.words:
        if x0_min <= w.x0 <= x0_max and DATE_RE.match(w.text):
            return w.text
    return None


def _is_stay_date_row(row: Row) -> bool:
    text = row.text_in_range(x0=None, x1=LABEL_VALUE_BOUNDARY)
    return "Stay" in text and "Date" in text


def _is_record_anchor(row: Row) -> tuple[str, str] | None:
    """Return (status, arrival_date) if this row starts a new guest record."""
    status = _find_status_word(row)
    arrival = _find_date_word(row, 325, 430)
    if status and arrival:
        return status, arrival
    return None


def _normalize_label(text: str) -> str:
    """Collapse whitespace and remove spaces before ':' so 'Last Checkout
    Date :' and 'Last Checkout Date:' compare equal."""
    return re.sub(r"\s+", " ", text).replace(" :", ":").strip().rstrip(":")


_NORMALIZED_LABEL_FIELD_MAP = {_normalize_label(label): field for label, field in LABEL_FIELD_MAP.items()}


def _match_label(row: Row) -> tuple[str, str] | None:
    """If this row's left side (x0 < boundary) is a known label, return
    (field_name, rest_of_row_text). Handles multi-word labels like
    'Comments / Notes:' and inline multi-label rows like
    'Last Stay Property: X  Lifetime Revenue: $Y ...'."""
    label_text = row.text_in_range(x0=None, x1=LABEL_VALUE_BOUNDARY).strip()
    if not label_text:
        return None
    field = _NORMALIZED_LABEL_FIELD_MAP.get(_normalize_label(label_text))
    if field:
        value = row.text_in_range(x0=LABEL_VALUE_BOUNDARY).strip()
        return field, value
    return None


def _split_inline_labels(text: str) -> dict[str, str]:
    """Split a row like 'CODE  Lifetime Revenue: $5,000  Lifetime Stays: 3
    Lifetime Nights: 10' into {'last_stay_property': 'CODE',
    'lifetime_revenue': '$5,000', ...}."""
    result: dict[str, str] = {}
    positions = []
    for label in INLINE_LABELS:
        idx = text.find(label)
        if idx != -1:
            positions.append((idx, label))
    positions.sort()

    if not positions:
        return {"last_stay_property": text.strip()} if text.strip() else {}

    first_idx = positions[0][0]
    prefix = text[:first_idx].strip()
    if prefix:
        result["last_stay_property"] = prefix

    for i, (idx, label) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        value = text[idx + len(label):end].strip()
        result[INLINE_LABEL_FIELD_MAP[label]] = value

    return result


def _parse_booking_agency_row(text: str) -> dict[str, str]:
    idx = text.find("IATA:")
    if idx == -1:
        return {"booking_agency": text.strip()}
    agency = text[:idx].strip()
    iata = text[idx + len("IATA:"):].strip()
    return {"booking_agency": agency, "iata": iata}


class _RecordBuilder:
    """Accumulates rows for one guest record until finalized."""

    def __init__(self, status: str, arrival_date: str, source_page: int):
        self.status = status
        self.arrival_date = arrival_date
        self.source_page = source_page
        self.room_name: str | None = None
        self.guest_name: str = ""
        self.guests_count: int | None = None
        self.guests_share: int | None = None
        self.room_type: str | None = None
        self.confirmation_number: str | None = None
        self.departure_date: str | None = None
        self.fields: dict[str, list[str]] = {}
        self.active_field: str | None = None
        self.warnings: list[str] = []
        self._anchor_row_consumed = False
        self._detail_row_consumed = False

    def consume_anchor_row(self, row: Row) -> None:
        room_words = [w for w in row.words if w.x0 < 100]
        self.room_name = " ".join(w.text for w in room_words).strip() or None

        name_words = [w for w in row.words if 100 <= w.x0 < 235]
        self.guest_name = " ".join(w.text for w in name_words).strip()

        share_words = [w for w in row.words if 435 <= w.x0 <= 460 and w.text != "/"]
        if len(share_words) >= 1 and share_words[0].text.isdigit():
            self.guests_count = int(share_words[0].text)
        if len(share_words) >= 2 and share_words[1].text.isdigit():
            self.guests_share = int(share_words[1].text)

    def consume_detail_row(self, row: Row) -> None:
        room_type_words = [w for w in row.words if w.x0 < 100]
        if room_type_words:
            self.room_type = " ".join(w.text for w in room_type_words).strip()

        conf_words = [w for w in row.words if 100 <= w.x0 < 235]
        conf_text = " ".join(w.text for w in conf_words).strip()
        if conf_text:
            self.confirmation_number = conf_text

        self.departure_date = _find_date_word(row, 325, 430)

    def append_field_text(self, field: str, text: str) -> None:
        if not text:
            return
        self.fields.setdefault(field, []).append(text)

    def finalize(self) -> GuestRecord:
        flags = list(self.warnings)
        if self.room_type and not self.room_name:
            flags.append("missing_room_name")
        if self.status not in KNOWN_STATUSES:
            flags.append(f"unknown_status:{self.status}")

        def joined(field: str) -> str:
            parts = self.fields.get(field, [])
            return "\n\n".join(parts) if field == "comments_notes" else " ".join(parts)

        return GuestRecord(
            confirmation_number=self.confirmation_number or "",
            guest_name=self.guest_name,
            room_name=self.room_name or "",
            room_type=self.room_type or "",
            status=self.status,
            arrival_date=self.arrival_date,
            departure_date=self.departure_date or "",
            guests_count=self.guests_count,
            guests_share=self.guests_share,
            source_page=self.source_page,
            vip_level=joined("vip_level"),
            address=joined("address"),
            preferences=joined("preferences"),
            last_stay_property=joined("last_stay_property"),
            last_checkout_date=joined("last_checkout_date"),
            lifetime_revenue=joined("lifetime_revenue"),
            lifetime_stays=joined("lifetime_stays"),
            lifetime_nights=joined("lifetime_nights"),
            booking_agency=joined("booking_agency"),
            iata=joined("iata"),
            guest_notes=joined("guest_notes"),
            reservation_notes=joined("reservation_notes"),
            comments_notes=joined("comments_notes"),
            flags=flags,
        )


def parse_guest_pdf(path: str) -> list[GuestRecord]:
    records: list[GuestRecord] = []
    builder: _RecordBuilder | None = None
    expect_detail_row = False
    reported_total: int | None = None

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            rows = _extract_rows(page)
            for row in rows:
                text = row.text_in_range()
                if not text.strip():
                    continue

                total_match = re.search(r"Total Reservations\s+(\d+)", text)
                if total_match:
                    reported_total = int(total_match.group(1))

                if _is_boilerplate(row):
                    continue

                anchor = _is_record_anchor(row)
                if anchor:
                    if builder is not None:
                        records.append(builder.finalize())
                    status, arrival_date = anchor
                    builder = _RecordBuilder(status, arrival_date, page_index)
                    builder.consume_anchor_row(row)
                    expect_detail_row = True
                    continue

                if builder is None:
                    continue

                if expect_detail_row:
                    builder.consume_detail_row(row)
                    expect_detail_row = False
                    continue

                if _is_stay_date_row(row):
                    continue

                label_match = _match_label(row)
                if label_match:
                    field, value = label_match
                    if field == "last_stay_property":
                        for f, v in _split_inline_labels(value).items():
                            builder.append_field_text(f, v)
                        builder.active_field = None
                    elif field == "booking_agency":
                        for f, v in _parse_booking_agency_row(value).items():
                            builder.append_field_text(f, v)
                        builder.active_field = None
                    else:
                        builder.append_field_text(field, value)
                        builder.active_field = field if field in CONTINUATION_FIELDS else None
                    continue

                left_text = row.text_in_range(x0=None, x1=LABEL_VALUE_BOUNDARY).strip()
                if not left_text and builder.active_field:
                    value = row.text_in_range(x0=LABEL_VALUE_BOUNDARY).strip()
                    builder.append_field_text(builder.active_field, value)
                    continue

                if not left_text:
                    continue

                builder.warnings.append(f"unrecognized_row:{text[:80]!r}")

    if builder is not None:
        records.append(builder.finalize())

    if reported_total is not None and reported_total != len(records):
        for r in records:
            r.flags.append(
                f"count_mismatch: parsed {len(records)} vs report total {reported_total}"
            )

    return records
