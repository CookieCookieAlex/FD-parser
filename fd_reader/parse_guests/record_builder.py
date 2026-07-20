"""Label matching and the per-guest record accumulator for the
guest-arrivals PDF. See the package docstring
(fd_reader/parse_guests/__init__.py) for the overall parsing strategy.
"""
from __future__ import annotations

import re

from fd_reader.models import GuestRecord
from fd_reader.parse_guests.rows import LABEL_VALUE_BOUNDARY, Row, find_date_word

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


def _normalize_label(text: str) -> str:
    """Collapse whitespace and remove spaces before ':' so 'Last Checkout
    Date :' and 'Last Checkout Date:' compare equal."""
    return re.sub(r"\s+", " ", text).replace(" :", ":").strip().rstrip(":")


_NORMALIZED_LABEL_FIELD_MAP = {_normalize_label(label): field for label, field in LABEL_FIELD_MAP.items()}


def match_label(row: Row) -> tuple[str, str] | None:
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


def split_inline_labels(text: str) -> dict[str, str]:
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


def parse_booking_agency_row(text: str) -> dict[str, str]:
    idx = text.find("IATA:")
    if idx == -1:
        return {"booking_agency": text.strip()}
    agency = text[:idx].strip()
    iata = text[idx + len("IATA:"):].strip()
    return {"booking_agency": agency, "iata": iata}


class RecordBuilder:
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

        self.departure_date = find_date_word(row, 325, 430)

    def append_field_text(self, field: str, text: str) -> None:
        if not text:
            return
        self.fields.setdefault(field, []).append(text)

    def consume_label_row(self, field: str, value: str) -> None:
        """Apply one matched label/value row (from match_label) to this
        record, handling the two labels whose value packs multiple
        sub-fields into a single row."""
        if field == "last_stay_property":
            for f, v in split_inline_labels(value).items():
                self.append_field_text(f, v)
            self.active_field = None
        elif field == "booking_agency":
            for f, v in parse_booking_agency_row(value).items():
                self.append_field_text(f, v)
            self.active_field = None
        else:
            self.append_field_text(field, value)
            self.active_field = field if field in CONTINUATION_FIELDS else None

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
