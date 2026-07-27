"""Cross-check a guest's pet-amenities note call-out (match/perks.py's
is_pet_amenities -- dog coming in) against whether their assigned room is
even allowed to have one.

Policy: dogs are only allowed in Cabins (rooms/directory.py's
category="Cabins"), capped at 2 per cabin. The note text only tells us a
dog is present, not how many, so this check can't verify the 2-per-cabin
cap -- it only flags the harder violation: a dog in a non-Cabin room at
all, which needs a human to go check whether it's a service dog (which
would exempt this) before anything else happens.

No pet-amenities mention found, or no room assigned yet -> check_pet_room
returns None, same "no signal" contract as check_capacity/check_sofa_bed.
"""
from __future__ import annotations

from dataclasses import dataclass

from fd_reader.match.perks import is_pet_amenities
from fd_reader.models import GuestRecord
from fd_reader.rooms.directory import by_abbreviation

CABIN_CATEGORY = "Cabins"


@dataclass
class PetRoomCheck:
    guest: GuestRecord
    room_category: str


def check_pet_room(guest: GuestRecord) -> PetRoomCheck | None:
    """None if no pet-amenities mention is found, the room is unknown, or
    the assigned room is a Cabin (dogs allowed) -- callers should treat
    None as "no violation found," not as "confirmed pet-friendly room"."""
    if not is_pet_amenities(guest):
        return None
    if not guest.room_name:
        return None
    room = by_abbreviation(guest.room_name.strip())
    if room is None:
        return None
    if room.category == CABIN_CATEGORY:
        return None
    return PetRoomCheck(guest=guest, room_category=room.category)
