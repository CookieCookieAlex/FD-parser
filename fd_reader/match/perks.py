"""Detect perk call-outs (Virtuoso, breakfast-included, pet amenities) from
a guest's raw note text -- informational only, not reservation-matching
signals.
"""
from __future__ import annotations

import re

from fd_reader.models import GuestRecord, all_notes_text

VIRTUOSO_RE = re.compile(r"virtuoso", re.IGNORECASE)
BREAKFAST_RE = re.compile(r"breakfast\s+incl\w*", re.IGNORECASE)  # tolerates "INCLLUDED" typo
PET_AMENITIES_RE = re.compile(r"pet\s+(amenit\w*|friendly)", re.IGNORECASE)


def is_virtuoso(guest: GuestRecord) -> bool:
    return bool(VIRTUOSO_RE.search(all_notes_text(guest)))


def is_breakfast_included(guest: GuestRecord) -> bool:
    return bool(BREAKFAST_RE.search(all_notes_text(guest)))


def is_pet_amenities(guest: GuestRecord) -> bool:
    return bool(PET_AMENITIES_RE.search(all_notes_text(guest)))
