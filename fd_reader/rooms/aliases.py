"""Resolve a Yelp `Notes & Tags` room-code hint to a `rooms/directory.py` Room.

`ReservationRecord.room_code_hint` (see parsing/reservations/fields.py) is
raw leftover text from Notes & Tags after the restaurant keyword and
outside-guest phrases are stripped -- e.g. "'s AUSABL", "'s lookout lg",
"S ST ARM SADDLE", "s tamarack lg". Staff hand-type the guest-list room
name/abbreviation into Yelp notes as their own manual cross-reference, so
this is often a better join key than guest name, but the spelling is
inconsistent against the PMS room codes in `rooms/directory.py`
(abbreviated, punctuated, upper/lowercased, sometimes with extra words
like "lg"/"outside"/allergy notes mixed in).

Matching tokenizes and checks whole words against room abbreviations and
full-name words rather than a raw substring search, which would
false-positive short abbreviations like "S" and would silently mis-resolve
non-room text like "Runway"/"Wine Cellar" that isn't one of the 32 rooms in
rooms/directory.py. See CLAUDE.md for the full room-alias background;
expect to keep growing `_KNOWN_MISSPELLINGS` as new hint spellings show up.
"""
from __future__ import annotations

import re

from fd_reader.rooms.directory import ROOMS, Room

# Leftover possessive fragments from "Artisans'"/"Maggie's" that
# extract_room_code_hint() (parsing/reservations/fields.py) doesn't strip,
# since it only strips the "artisan"/"maggie" keyword itself, not the
# surrounding apostrophe-s. Stripped as a leading token before word-matching.
_LEADING_NOISE_RE = re.compile(r"^'?s\b\s*", re.IGNORECASE)

# Spellings seen in real Notes & Tags text that don't tokenize cleanly to
# the room's own name/abbreviation (typos, contractions, alternate
# spellings). Left-hand side is the normalized (uppercase, letters-only)
# token; right-hand side is the room abbreviation it should resolve to.
_KNOWN_MISSPELLINGS: dict[str, str] = {
    "KIWSSA": "KIWA",       # "'s Kiwssa" -> Kiwassa
    "HEARTHIDE": "HEARTH",  # "'s Hearthide ..." -> Hearthside
    "AUSABLE": "AUSABL",    # "s ausable would like outside" -> Ausable
    "TAMARACK": "TAMAR",    # "s tamarack lg" -> Tamarac
}

# Non-room venues/activities that legitimately show up in Notes & Tags but
# are NOT one of the 32 rooms in rooms/directory.py -- confirmed by checking
# these tokens don't appear anywhere else in the project as a room
# reference. Listed so a future word-match near-miss doesn't get silently
# mapped to the wrong room; these should always resolve to no match.
NON_ROOM_TERMS = {"RUNWAY", "WINECELLAR", "WINE", "CELLAR", "PUB"}


def _normalize(text: str) -> str:
    text = _LEADING_NOISE_RE.sub("", text)
    return text.strip()


def _candidate_tokens(text: str) -> list[str]:
    """Word-level tokens (letters only, uppercased) plus adjacent-word
    2- and 3-grams (e.g. "ST REGIS" -> "STREGIS", "ST ARM" -> "STARM"),
    since several room full names are two words ("St. Regis", "St.
    Armand") and staff often type them with a space, not squashed
    together.

    Ordered so multi-word grams (more specific, e.g. "STARMAND") are tried
    before single words, and within the same gram size, earlier-occurring
    words win -- when a hint mentions two rooms (e.g. "Marble Ampersand",
    a family/adjacent booking), this makes resolution deterministic and
    picks the first-mentioned room rather than whichever happens to sort
    last, matching the "only the first is resolved" behavior noted in the
    module docstring."""
    words = [w.upper() for w in re.findall(r"[A-Za-z]+", text)]
    grams: list[tuple[int, int, str]] = []
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            grams.append((n, i, "".join(words[i : i + n])))
    grams.sort(key=lambda g: (-g[0], g[1]))
    return [token for _, _, token in grams]


def _room_full_name_key(room: Room) -> str:
    return re.sub(r"[^A-Za-z]", "", room.full_name).upper()


def resolve_room_code_hint(hint: str | None) -> Room | None:
    """Best-effort resolve a raw `room_code_hint` string to a Room.

    Returns None if no room can be confidently identified (ambiguous,
    no room-looking token present, or the hint refers to a non-room term
    like "Runway"/"Wine Cellar"). Callers should treat None as "no
    room-code signal available" and fall back to fuzzy name matching, not
    as an error.
    """
    if not hint:
        return None

    normalized = _normalize(hint)
    tokens = _candidate_tokens(normalized)

    abbrev_by_code = {room.abbreviation: room for room in ROOMS if room.abbreviation}
    full_name_by_key = {_room_full_name_key(room): room for room in ROOMS}

    for token in tokens:
        if token in NON_ROOM_TERMS:
            continue
        if token in _KNOWN_MISSPELLINGS:
            code = _KNOWN_MISSPELLINGS[token]
            if code in abbrev_by_code:
                return abbrev_by_code[code]
        if token in abbrev_by_code:
            return abbrev_by_code[token]
        if token in full_name_by_key:
            return full_name_by_key[token]

    return None
