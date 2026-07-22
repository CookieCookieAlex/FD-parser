"""Flag guest-list records where guests_count exceeds the assigned room's
physical sleeping capacity (see rooms/directory.py's Room.max_guests) --
a guest-list-only data-quality check, independent of Yelp matching.

guest.room_name is looked up directly against Room.abbreviation, not
resolved through rooms/aliases.py's fuzzy Yelp-notes matching, since the
guest list already stores the exact PMS room code.
"""
from __future__ import annotations

from dataclasses import dataclass

from fd_reader.models import GuestRecord
from fd_reader.rooms.directory import by_abbreviation


@dataclass
class CapacityCheck:
    guest: GuestRecord
    max_guests: int
    actual_guests: int


def check_capacity(guest: GuestRecord) -> CapacityCheck | None:
    """None if the room is unknown, has no confirmed max_guests, or the
    guest count doesn't exceed it -- callers should treat None as "no
    capacity signal available," not as "under capacity confirmed"."""
    if not guest.room_name or guest.guests_count is None:
        return None
    room = by_abbreviation(guest.room_name.strip())
    if room is None or room.max_guests is None:
        return None
    if guest.guests_count <= room.max_guests:
        return None
    return CapacityCheck(guest=guest, max_guests=room.max_guests, actual_guests=guest.guests_count)
