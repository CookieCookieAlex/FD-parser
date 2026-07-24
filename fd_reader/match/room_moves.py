"""Detect room moves: same guest name, one record's departure_date exactly
equals another's arrival_date (no off-by-one tolerance), AND both room name
and room type change between the two records. If only the room name
changes but the room type stays the same (e.g. a same-category
reassignment), it's not treated as a move.

Records are linked, never merged -- confirmation number is per-stay, not
per-guest (see rooms/directory.py's module docstring).
"""
from __future__ import annotations

from dataclasses import dataclass

from fd_reader.models import GuestRecord
from fd_reader.util import group_by


@dataclass
class RoomMove:
    guest_name: str
    earlier: GuestRecord
    later: GuestRecord


def detect_room_moves(guests: list[GuestRecord]) -> list[RoomMove]:
    by_name = group_by(guests, lambda g: g.guest_name.strip().lower())

    moves: list[RoomMove] = []
    for records in by_name.values():
        if len(records) < 2:
            continue
        for earlier in records:
            for later in records:
                if earlier is later:
                    continue
                if earlier.departure_date != later.arrival_date:
                    continue
                if earlier.room_name == later.room_name:
                    continue
                if earlier.room_type == later.room_type:
                    continue
                moves.append(
                    RoomMove(guest_name=earlier.guest_name, earlier=earlier, later=later)
                )

    return moves
