"""Canonical room directory for Lake Placid Lodge.

This is the reference list the user is filling in by hand (they have the
authoritative source). Once filled in, this becomes:

  - ground truth for the guest-list parser's `room_name`/`room_type`
    columns (validate/normalize what pdfplumber reads off the PMS report)
  - the basis for `fd_reader/room_aliases.py` (Yelp-notes-shorthand -> PMS
    room code), since every alias should resolve to one of these entries
  - the room+room-type-change signal for "actual room move" detection
    (see match.py design note below): a room move requires BOTH the room
    name AND room type to change between two date-adjacent records for the
    same guest -- if room type stays the same, it's a same-category
    reassignment, not treated as a move for now unless told otherwise.

Fields per room:
  full_name        -- the proper name as used in conversation/paperwork
  abbreviation      -- the short code that appears in the room-name column
                       of the arrivals PDF (confirmed = seen in real sample
                       data; otherwise None until filled in)
  room_type_code    -- the short room-TYPE code shared by rooms of the same
                       kind (e.g. "1KV", "1KF", "LL1KF") -- confirmed from
                       sample data where available
  room_type_desc    -- full description of what that room type means
  key_number        -- 1-3 digit physical key number
  phone_number      -- 3-digit extension
  category          -- Cabins / Lakeside / Main Lodge / Overlook

`abbreviation` and `room_type_code` are pre-filled only where they were
directly observed in guest-notes/arrival_notes.pdf and
guest-notes/arrivals-notes-6days-advance.pdf. Everything else is left as
None -- fill in as the user provides the real reference list.
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


ROOMS: list[Room] = [
    # --- Cabins ---
    Room(full_name="Buck", category="Cabins", abbreviation="BUCK", room_type_code="2KKF",
         room_type_desc="Two Bedroom King/King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Hawk", category="Cabins", abbreviation="HAWK", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Kiwassa", category="Cabins", abbreviation="KIWA", room_type_code="2KTV",
         room_type_desc="Two Bedroom King/Two Twins Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Marble", category="Cabins", abbreviation="MARBLE", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Lookout", category="Cabins", abbreviation="LOOK", room_type_code="2KTV",
         room_type_desc="Two Bedroom King/Two Twins Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Ampersand", category="Cabins", abbreviation="AMPER", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Tahawas", category="Cabins", abbreviation="TAHAW", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Mckenzie", category="Cabins", abbreviation="MCKEN", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="St. Armand", category="Cabins", abbreviation="STARM", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Moss Cliff", category="Cabins", abbreviation="MOSS", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Rondeau", category="Cabins", abbreviation="ROND", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Eagles", category="Cabins", abbreviation="EAGLES", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Colden", category="Cabins", abbreviation="COLDEN", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Whitney", category="Cabins", abbreviation="WHIT", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Saddleback", category="Cabins", abbreviation="SADDLE", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="McIntyre", category="Cabins", abbreviation="MCINT", room_type_code="1KF",
         room_type_desc="One Bedroom King Cabin-LakeFront",
         key_number=None, phone_number=None),
    Room(full_name="Mt. Marcy", category="Cabins", abbreviation="MTMARCY", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Mt. Jo", category="Cabins", abbreviation="MTJO", room_type_code="1KV",
         room_type_desc="One Bedroom King Cabin-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Owls Head", category="Cabins", abbreviation="OWLS", room_type_code="1OKF",
         room_type_desc="One Bedroom King/Two Twins Cabin-LakeFront",
         key_number=None, phone_number=None),

    # --- Lakeside ---
    Room(full_name="Placid", category="Lakeside", abbreviation="PLACID", room_type_code="LU1KF",
         room_type_desc="Upper Level One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),
    Room(full_name="Ausable", category="Lakeside", abbreviation="AUSABL", room_type_code="LU1KF",
         room_type_desc="Upper Level One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),
    Room(full_name="Raquette", category="Lakeside", abbreviation="RAQTTE", room_type_code="L1KF",
         room_type_desc="One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),
    Room(full_name="Cascade", category="Lakeside", abbreviation="CASCDE", room_type_code="L1KF",
         room_type_desc="One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),
    Room(full_name="Stillwater", category="Lakeside", abbreviation="STLWTR", room_type_code="LL1KF",
         room_type_desc="Lower Level One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),
    Room(full_name="Loon", category="Lakeside", abbreviation="LOON", room_type_code="LL1KF",
         room_type_desc="Lower Level One Bedroom King Suite-Lakeside",
         key_number=None, phone_number=None),

    # --- Main Lodge ---
    Room(full_name="Tamarac", category="Main Lodge", abbreviation="TAMAR", room_type_code="MKV",
         room_type_desc="Main Lodge King-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="St. Regis", category="Main Lodge", abbreviation="STREG", room_type_code="MKV",
         room_type_desc="Main Lodge King-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Hearthside", category="Main Lodge", abbreviation="HEARTH", room_type_code="MKVA",
         room_type_desc="Mobility Accessible Main Lodge King-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Treetop", category="Main Lodge", abbreviation="TREE", room_type_code="MTKV",
         room_type_desc="Main Lodge: Treetop-Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Whiteface", category="Main Lodge", abbreviation="WTFACE", room_type_code="MWKV",
         room_type_desc="Main Lodge: Whiteface-Lake View",
         key_number=None, phone_number=None),

    # --- Overlook ---
    Room(full_name="Pine", category="Overlook", abbreviation="PINE", room_type_code="SPKP",
         room_type_desc="Overlook Partial Lake View",
         key_number=None, phone_number=None),
    Room(full_name="Birch", category="Overlook", abbreviation="BIRCH", room_type_code="SBKP",
         room_type_desc="Overlook Partial Lake View",
         key_number=None, phone_number=None),
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
