"""Cross-check the guest-arrivals list against Yelp restaurant reservations.

- name_matching.py: match each Yelp reservation to an in-house guest by name
  (room/time are secondary confirm/flag signals, checked after).
- notes_cross_check.py: compare what a guest's free-text notes say about
  restaurant reservations against what Yelp actually shows for them.
- room_groups.py / room_moves.py: multi-room family bookings and same-guest
  room changes across adjacent stays.
- perks.py / capacity_check.py / sofa_bed_check.py: guest-list-only signals
  (perk call-outs, guest count vs. room capacity, sofa-bed request vs.
  whether the assigned room actually has one).
"""
from __future__ import annotations

from fd_reader.match.capacity_check import CapacityCheck, check_capacity
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
from fd_reader.match.perks import is_breakfast_included, is_pet_amenities, is_virtuoso
from fd_reader.match.room_groups import RoomGroup, find_room_groups
from fd_reader.match.room_moves import RoomMove, detect_room_moves
from fd_reader.match.sofa_bed_check import SofaBedCheck, check_sofa_bed, requests_sofa_bed

__all__ = [
    "AMBIGUITY_MARGIN",
    "FUZZY_NAME_THRESHOLD",
    "MatchResult",
    "match_reservations",
    "NOTE_FIELDS",
    "NoteCrossCheck",
    "cross_check_notes",
    "CapacityCheck",
    "check_capacity",
    "is_breakfast_included",
    "is_pet_amenities",
    "is_virtuoso",
    "RoomGroup",
    "find_room_groups",
    "RoomMove",
    "detect_room_moves",
    "SofaBedCheck",
    "check_sofa_bed",
    "requests_sofa_bed",
]
