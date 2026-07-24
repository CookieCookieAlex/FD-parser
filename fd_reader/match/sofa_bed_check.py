"""Cross-reference a guest's note-text sofa-bed REQUEST against whether
their actual room has one (rooms/directory.py's Room.has_sofa_bed).

Two outcomes when a request is found in any of the three free-text note
fields:
  - the assigned room has a sofa bed -- informational confirmation, not a
    problem (SofaBedCheck.satisfied=True).
  - the assigned room does NOT have one -- a real staff action item (likely
    needs a room move before arrival), flagged distinctly from
    match/capacity_check.py's over-capacity check since the room being
    "full" and the room "not having the amenity a guest explicitly asked
    for" are different problems with different fixes.

No request found -> check_sofa_bed returns None, same "no signal" contract
as check_capacity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fd_reader.models import GuestRecord, all_notes_text
from fd_reader.rooms.directory import by_abbreviation

# Tolerant of the real staff phrasing variants seen for "please put an
# extra sleeping surface in this room" -- not just "sofa bed" itself:
#   - sofa bed / sofabed / sofa-bed
#   - pull-out / pullout (bed/couch/sofa, or bare)
#   - sleeper sofa / sofa sleeper
#   - rollaway (bed)
#   - extra bed / additional bed
#   - fold-out / foldout (bed/couch/sofa)
#   - cot / cots -- the fold-up/collapsible portable bed (word-boundaried
#     so it doesn't match inside "Scott", "cottage", "mascot", etc.)
# "couch"/"bed" alone are deliberately NOT matched on their own -- too
# broad, would false-positive on unrelated text (e.g. "comfortable bed").
SOFA_BED_REQUEST_RE = re.compile(
    r"sofa[\s-]?bed"
    r"|pull[\s-]?out"
    r"|sleeper\s+sofa|sofa\s+sleeper"
    r"|roll[\s-]?away"
    r"|(extra|additional)\s+bed"
    r"|fold[\s-]?out"
    r"|\bcots?\b",
    re.IGNORECASE,
)


@dataclass
class SofaBedCheck:
    guest: GuestRecord
    satisfied: bool  # True: room has a sofa bed. False: requested but room doesn't have one.


def requests_sofa_bed(guest: GuestRecord) -> bool:
    return bool(SOFA_BED_REQUEST_RE.search(all_notes_text(guest)))


def check_sofa_bed(guest: GuestRecord) -> SofaBedCheck | None:
    """None if no sofa-bed request is mentioned in any note field, or the
    guest has no room assigned yet -- callers should treat None as "no
    request found," not as "room confirmed to have one"."""
    if not requests_sofa_bed(guest):
        return None
    if not guest.room_name:
        return None
    room = by_abbreviation(guest.room_name.strip())
    if room is None:
        return None
    return SofaBedCheck(guest=guest, satisfied=room.has_sofa_bed)
