"""Derive restaurant identity, outside-guest status, and a room-code hint
out of a reservation row's raw `Notes & Tags` text -- see the package
docstring for why this can't come from the filename/page title.
"""
from __future__ import annotations

import re

from fd_reader.restaurants import RESTAURANT_KEYWORDS, find_restaurant

# Seen in Notes & Tags for reservations that aren't tied to any in-house
# guest at all (e.g. "Guest R -- artisans off property no allergies").
OUTSIDE_GUEST_KEYWORDS = ("off property", "og", "outside guest")

# Short internal shorthand seen in Notes & Tags (GH, hg, LM, EK, sz) --
# meaning isn't fully known and isn't needed for matching; stripped out of
# the room-code hint but not decoded.
_SHORTHAND_TOKENS = {"gh", "hg", "lm", "ek", "sz"}


def derive_restaurant(notes_tags: str) -> str | None:
    return find_restaurant(notes_tags)


def is_outside_guest(notes_tags: str) -> bool:
    lowered = notes_tags.lower()
    return any(keyword in lowered for keyword in OUTSIDE_GUEST_KEYWORDS)


def extract_room_code_hint(notes_tags: str) -> str | None:
    text = notes_tags
    for keyword in RESTAURANT_KEYWORDS:
        text = re.sub(keyword, "", text, flags=re.IGNORECASE)
    for keyword in OUTSIDE_GUEST_KEYWORDS:
        text = re.sub(re.escape(keyword), "", text, flags=re.IGNORECASE)
    tokens = re.split(r"[\s,.\-]+", text)
    kept = [t for t in tokens if t and t.lower() not in _SHORTHAND_TOKENS]
    hint = " ".join(kept).strip(" -,.")
    return hint or None
