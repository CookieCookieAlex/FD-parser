"""Cross-check the guest-arrivals list against Yelp restaurant reservations.

Two independent things happen here, both described in CLAUDE.md's
"Matching strategy" and "Guest-list data-quality checks" sections:

1. Guest <-> Yelp matching (name_matching.py): for each Yelp
   ReservationRecord, find which in-house GuestRecord it belongs to.
   Primary key is guest name (surname-led, date-scoped to who's in-house
   that day); room and time are secondary confirm/flag signals checked
   AFTER the guest is already decided by name, never used to pick who the
   guest is. This answers "does this Yelp reservation correspond to a real
   in-house guest, and does everything else about it (room, party size)
   line up?"

2. Notes <-> Yelp cross-check (notes_cross_check.py): for each GuestRecord,
   extract restaurant mentions out of its free-text note fields
   (fd_reader.parse_notes) and compare them against the Yelp reservations
   actually found for that guest. This answers "does what staff wrote in
   the guest notes actually match what's in Yelp?" -- covering all four
   cases: note mentions a reservation Yelp doesn't have; Yelp has a
   reservation the notes don't mention; both exist but the date/time
   disagree; neither exists (no dinner reservation at all, not a problem
   by itself).

Also here: room_groups.py (multi-room family bookings), room_moves.py
(same guest, adjacent stays, different room), and perks.py (Virtuoso /
breakfast-included detection from note text) -- all independent,
guest-list-only signals that feed into the report alongside the two checks
above.
"""
from __future__ import annotations

from fd_reader.match.name_matching import (
    AMBIGUITY_MARGIN,
    FUZZY_NAME_THRESHOLD,
    MatchResult,
    match_reservations,
)
from fd_reader.match.notes_cross_check import (
    NOTE_FIELDS,
    NoteCrossCheck,
    cross_check_notes,
)
from fd_reader.match.perks import is_breakfast_included, is_virtuoso
from fd_reader.match.room_groups import RoomGroup, find_room_groups
from fd_reader.match.room_moves import RoomMove, detect_room_moves

__all__ = [
    "AMBIGUITY_MARGIN",
    "FUZZY_NAME_THRESHOLD",
    "MatchResult",
    "match_reservations",
    "NOTE_FIELDS",
    "NoteCrossCheck",
    "cross_check_notes",
    "is_breakfast_included",
    "is_virtuoso",
    "RoomGroup",
    "find_room_groups",
    "RoomMove",
    "detect_room_moves",
]
