"""Shared synthetic-data helpers for tests_synthetic/.

Unlike tests/, nothing here reads real guest data from guest-notes/. Guest
names used across this suite are entirely made up: common first names
(John, Emma, Steve, ...) paired with well-known last names borrowed from
public figures (Jackson, Sheeran, Depp, ...), purely as memorable, obviously-
fake placeholders -- not references to any real hotel guest.
"""
from __future__ import annotations

from fd_reader.models import GuestRecord
from fd_reader.parsing.guests.rows import Row as GuestRow
from fd_reader.parsing.guests.rows import Word as GuestWord
from fd_reader.parsing.reservations import ReservationRecord
from fd_reader.parsing.reservations import Row as YelpRow
from fd_reader.parsing.reservations import Word as YelpWord

# Fake guest names: "First, Last" to match the PMS "Last, First" storage
# order used throughout GuestRecord.guest_name.
FAKE_GUESTS = [
    "Jackson, John",
    "Sheeran, Steve",
    "Depp, Emma",
    "Hanks, Laura",
    "Swift, Michael",
    "Clarkson, Olivia",
    "Bieber, Daniel",
    "Cyrus, Sophia",
]


def guest_name(last_first: str) -> str:
    """Pass through a 'Last, First' string from FAKE_GUESTS unchanged --
    exists just to make call sites read clearly."""
    return last_first


# ---------------------------------------------------------------------------
# Guest-arrivals Row/Word builders (fd_reader.parsing.guests column bands:
# room name x0<100, guest name 100<=x0<235, status 235<=x0<=330,
# arrival/departure date 325<=x0<=430, guests 435<=x0<=460,
# rate plan 490<=x0<574, label/value boundary at x0=160).
# ---------------------------------------------------------------------------


def guest_word(text: str, x0: float, top: float = 100.0) -> GuestWord:
    return GuestWord(text=text, x0=x0, x1=x0 + len(text) * 6, top=top, bottom=top + 10)


def guest_row(words: list[GuestWord], top: float = 100.0) -> GuestRow:
    return GuestRow(words=sorted(words, key=lambda w: w.x0), top=top)


def make_anchor_row(
    room_name: str,
    first_last: str,
    status: str = "Reserved",
    arrival_date: str = "07/10/2026",
    guests_count: str = "2",
    guests_share: str = "0",
    rate_plan: str = "LEIS",
    top: float = 100.0,
) -> GuestRow:
    words = []
    if room_name:
        words.append(guest_word(room_name, 40, top))
    last, first = [p.strip() for p in first_last.split(",", 1)]
    words.append(guest_word(f"{last},", 110, top))
    words.append(guest_word(first, 150, top))
    words.append(guest_word(status, 250, top))
    words.append(guest_word(arrival_date, 350, top))
    words.append(guest_word(guests_count, 440, top))
    words.append(guest_word("/", 448, top))
    words.append(guest_word(guests_share, 452, top))
    words.append(guest_word(rate_plan, 500, top))
    return guest_row(words, top)


def make_detail_row(
    room_type: str,
    confirmation_number: str,
    departure_date: str,
    top: float = 112.0,
) -> GuestRow:
    words = [
        guest_word(room_type, 40, top),
        guest_word(confirmation_number, 110, top),
        guest_word(departure_date, 350, top),
    ]
    return guest_row(words, top)


def make_label_row(label: str, value: str, top: float) -> GuestRow:
    words = [guest_word(label, 40, top)]
    x = 165.0
    for token in value.split(" "):
        words.append(guest_word(token, x, top))
        x += len(token) * 6 + 6
    return guest_row(words, top)


# ---------------------------------------------------------------------------
# Yelp reservation Row/Word builders (fd_reader.parsing.reservations column
# bands: time 40-95, party size 100-145, guest name 170-270, notes 275-355).
# ---------------------------------------------------------------------------


def yelp_word(text: str, x0: float, top: float = 100.0) -> YelpWord:
    return YelpWord(text=text, x0=x0, x1=x0 + len(text) * 6, top=top, bottom=top + 10)


def yelp_row(words: list[YelpWord], top: float = 100.0) -> YelpRow:
    return YelpRow(words=sorted(words, key=lambda w: w.x0), top=top)


def make_reservation_start_row(
    time_text: str,
    party_size: str,
    guest_name_text: str,
    notes: str = "",
    top: float = 100.0,
) -> YelpRow:
    words = [
        yelp_word(time_text, 50, top),
        yelp_word(party_size, 110, top),
        yelp_word(guest_name_text, 175, top),
    ]
    if notes:
        x = 280.0
        for token in notes.split(" "):
            words.append(yelp_word(token, x, top))
            x += len(token) * 6 + 6
    return yelp_row(words, top)


def make_phone_row(phone_paren: str, phone_rest: str, top: float) -> YelpRow:
    """phone_paren must match PHONE_RE (^\\(\\d{3}\\)$), e.g. '(518)'."""
    words = [yelp_word(phone_paren, 175, top), yelp_word(phone_rest, 200, top)]
    return yelp_row(words, top)


def make_notes_continuation_row(notes: str, top: float) -> YelpRow:
    words = []
    x = 280.0
    for token in notes.split(" "):
        words.append(yelp_word(token, x, top))
        x += len(token) * 6 + 6
    return yelp_row(words, top)


# ---------------------------------------------------------------------------
# Synthetic GuestRecord / ReservationRecord builders for match.py/report.py
# level tests (these operate on already-parsed records, no PDF/Row at all).
# ---------------------------------------------------------------------------


def make_guest(**overrides) -> GuestRecord:
    defaults = dict(
        confirmation_number="SYN-1",
        guest_name="Jackson, John",
        room_name="PINEVW",
        room_type="1KV",
        status="Reserved",
        arrival_date="07/10/2026",
        departure_date="07/12/2026",
        guests_count=2,
        guests_share=0,
        source_page=1,
    )
    defaults.update(overrides)
    return GuestRecord(**defaults)


def make_reservation(**overrides) -> ReservationRecord:
    defaults = dict(
        source_date="Jul 10, 2026",
        time="7:00",
        party_size=2,
        guest_name="John Jackson",
        phone="",
        notes_tags="artisans PINEVW",
        source_page=1,
        restaurant="Artisans",
        room_code_hint="PINEVW",
    )
    defaults.update(overrides)
    return ReservationRecord(**defaults)
