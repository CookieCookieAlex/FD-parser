"""Room data and Yelp-notes-to-room-code resolution.

directory.py holds the canonical Lake Placid Lodge room list (ground
truth for room name/type matching and capacity checks); aliases.py
resolves the free-text room-code hints staff type into Yelp's Notes &
Tags field against that list.
"""
from __future__ import annotations

from fd_reader.rooms.aliases import NON_ROOM_TERMS, resolve_room_code_hint
from fd_reader.rooms.directory import ROOMS, Room, by_abbreviation, by_full_name

__all__ = [
    "ROOMS",
    "Room",
    "by_abbreviation",
    "by_full_name",
    "NON_ROOM_TERMS",
    "resolve_room_code_hint",
]
