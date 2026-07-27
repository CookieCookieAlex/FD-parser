"""Canonical room directory for Lake Placid Lodge.

Serves as: ground truth for the guest-list parser's `room_name`/`room_type`
columns, the basis for rooms/aliases.py (Yelp-notes-shorthand -> PMS room
code), and the room+room-type-change signal for room-move detection (a move
requires BOTH room name and room type to change between date-adjacent
records for the same guest -- same room type is a same-category
reassignment, not a move).

max_guests is the physical sleeping capacity used by match/capacity_check.py
to flag guest counts that exceed it: 5 for Buck (2 kings + pull-out sofa),
4 for Kiwassa/Lookout (2 kings), 3 for Lake View cabins with a king + sofa
and all 6 Lakeside rooms, 2 for everything else (single king, no sofa).
None means capacity isn't confirmed -- no check runs for those rooms.

has_sofa_bed is a separate flag from max_guests>2 -- Kiwassa/Lookout also
sleep 4 but via two kings, not a sofa, so it can't be derived from
max_guests alone. True for Buck, every Lake View cabin (Hawk/Marble/
Ampersand/Tahawas/Mckenzie/Rondeau/Mt. Marcy), and all 6 Lakeside rooms.
Used by match/sofa_bed_check.py to cross-reference a guest's note-text
sofa-bed REQUEST against whether their actual room has one.

`abbreviation`/`room_type_code` are filled in only where directly observed
in the sample PDFs; everything else is None until confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Room:
    full_name: str
    category: str
    abbreviation: str | None = None
    room_type_code: str | None = None
    room_type_desc: str | None = None
    key_number: str | None = None
    phone_number: str | None = None
    max_guests: int | None = None
    has_sofa_bed: bool = False


ROOMS: list[Room] = [
    # --- Cabins ---
    Room(full_name="Buck", category="Cabins", abbreviation="BUCK", room_type_code="2KKF",
         room_type_desc="Two Bedroom King/King Cabin-LakeFront",
           max_guests=5, has_sofa_bed=True),
    Room(full_name="Hawk", category="Cabins", abbreviation="HAWK", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Kiwassa", category="Cabins", abbreviation="KIWA", room_type_code="2KTV",
         room_type_desc="Two Bedroom King/Two Twins Cabin-Lake View",
           max_guests=4),
    Room(full_name="Marble", category="Cabins", abbreviation="MARBLE", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Lookout", category="Cabins", abbreviation="LOOK", room_type_code="2KTV",
         room_type_desc="Two Bedroom King/Two Twins Cabin-Lake View",
           max_guests=4),
    Room(full_name="Ampersand", category="Cabins", abbreviation="AMPER", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Tahawas", category="Cabins", abbreviation="TAHAW", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Mckenzie", category="Cabins", abbreviation="MCKEN", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="St. Armand", category="Cabins", abbreviation="STARM", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Moss Cliff", category="Cabins", abbreviation="MOSS", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Rondeau", category="Cabins", abbreviation="ROND", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Eagles", category="Cabins", abbreviation="EAGLES", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Colden", category="Cabins", abbreviation="COLDEN", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Whitney", category="Cabins", abbreviation="WHIT", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Saddleback", category="Cabins", abbreviation="SADDLE", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="McIntyre", category="Cabins", abbreviation="MCINT", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
           max_guests=2),
    Room(full_name="Mt. Marcy", category="Cabins", abbreviation="MTMARCY", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Mt. Jo", category="Cabins", abbreviation="MTJO", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
           max_guests=2),
    Room(full_name="Owls Head", category="Cabins", abbreviation="OWLS", room_type_code="1OKF",
         room_type_desc="One Bedroom King Cabin:Owls Head-LakeFront",
           max_guests=2),

    # --- Lakeside ---
    Room(full_name="Placid", category="Lakeside", abbreviation="PLACID", room_type_code="LU1KF",
         room_type_desc="Upper Level One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Ausable", category="Lakeside", abbreviation="AUSABL", room_type_code="LU1KF",
         room_type_desc="Upper Level One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Raquette", category="Lakeside", abbreviation="RAQTTE", room_type_code="L1KF",
         room_type_desc="One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Cascade", category="Lakeside", abbreviation="CASCDE", room_type_code="L1KF",
         room_type_desc="One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Stillwater", category="Lakeside", abbreviation="STLWTR", room_type_code="LL1KF",
         room_type_desc="Lower Level One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),
    Room(full_name="Loon", category="Lakeside", abbreviation="LOON", room_type_code="LL1KF",
         room_type_desc="Lower Level One Bedroom King Suite-Lakeside",
           max_guests=3, has_sofa_bed=True),

    # --- Main Lodge ---
    Room(full_name="Tamarac", category="Main Lodge", abbreviation="TAMAR", room_type_code="MKV",
         room_type_desc="Main Lodge King-Lake View",
           max_guests=2),
    Room(full_name="St. Regis", category="Main Lodge", abbreviation="STREG", room_type_code="MKV",
         room_type_desc="Main Lodge King-Lake View",
           max_guests=2),
    Room(full_name="Hearthside", category="Main Lodge", abbreviation="HEARTH", room_type_code="MKVA",
         room_type_desc="Mobility Accessible Main Lodge King-Lake View",
           max_guests=2),
    Room(full_name="Treetop", category="Main Lodge", abbreviation="TREE", room_type_code="MTKV",
         room_type_desc="Main Lodge: Treetop-Lake View",
           max_guests=2),
    Room(full_name="Whiteface", category="Main Lodge", abbreviation="WTFACE", room_type_code="MWKV",
         room_type_desc="Main Lodge: Whiteface-Lake View",
           max_guests=2),

    # --- Overlook ---
    Room(full_name="Pine", category="Overlook", abbreviation="PINE", room_type_code="SPKP",
         room_type_desc="Overlook Partial Lake View",
           max_guests=2),
    Room(full_name="Birch", category="Overlook", abbreviation="BIRCH", room_type_code="SBKP",
         room_type_desc="Overlook Partial Lake View",
           max_guests=2),
]


def by_abbreviation(abbreviation: str) -> Room | None:
    for room in ROOMS:
        if room.abbreviation == abbreviation:
            return room
    return None


def by_full_name(full_name: str) -> Room | None:
    normalized = full_name.strip().lower()
    for room in ROOMS:
        if room.full_name.strip().lower() == normalized:
            return room
    return None
