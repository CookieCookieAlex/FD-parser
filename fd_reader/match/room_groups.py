"""Detect multi-room group bookings -- several GuestRecords booked into
different rooms at once for the same [arrival_date, departure_date], e.g. a
family/party booking (confirmed real: Guest B across
TAHAW/AMPER/MTJO). Distinct from a room move (see room_moves.py) -- these
stays overlap completely rather than chaining end-to-end.

Used by name_matching.py (a name+date tie among a group's own rooms isn't a
real ambiguity) and by fd_reader.report (to surface "also see room(s): ..."
pointers on every record in the group).
"""
from __future__ import annotations

from dataclasses import dataclass

from fd_reader.models import GuestRecord


@dataclass
class RoomGroup:
    """matched_by tells you WHY these records were linked:
      - "exact_name": identical guest_name (confirmed real: Guest B,
        Guest B across TAHAW/AMPER/MTJO; Guest H across
        WTFACE/TREE; Guest J across HAWK/LOON) -- high confidence.
      - "same_surname": same surname, same dates, but a DIFFERENT first
        name (e.g. "Guest X" and "Guest Y" arriving/departing
        together) -- also a family booking, per the user, but a softer
        signal than an identical name match since two unrelated guests
        could in principle share a surname and dates by coincidence.
        Not yet confirmed in the real sample data (no such case exists
        there as of this writing) -- added defensively per user request,
        not from an observed bug.
    """
    guest_name: str
    records: list[GuestRecord]
    matched_by: str = "exact_name"


def _surname(guest_name: str) -> str:
    """Guest-list names are consistently 'Last, First' (confirmed: every
    real sample-data name has a comma) -- take the part before the comma.
    Falls back to the last whitespace-separated token for any name that
    doesn't follow that format, rather than guessing wrong."""
    name = guest_name.strip()
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    parts = name.split()
    return parts[-1].strip().lower() if parts else name.lower()


def find_room_groups(guests: list[GuestRecord]) -> list[RoomGroup]:
    exact_key_to_records: dict[tuple[str, str, str], list[GuestRecord]] = {}
    for guest in guests:
        key = (guest.guest_name.strip().lower(), guest.arrival_date, guest.departure_date)
        exact_key_to_records.setdefault(key, []).append(guest)

    groups: list[RoomGroup] = []
    grouped_confirmations: set[str] = set()
    for records in exact_key_to_records.values():
        if len(records) > 1:
            groups.append(RoomGroup(guest_name=records[0].guest_name, records=records, matched_by="exact_name"))
            grouped_confirmations.update(r.confirmation_number for r in records)

    # Same surname + same dates, different first name -- only consider
    # guests not already claimed by an exact-name group above, so a
    # 3-room exact-name family isn't also re-grouped here.
    surname_key_to_records: dict[tuple[str, str, str], list[GuestRecord]] = {}
    for guest in guests:
        if guest.confirmation_number in grouped_confirmations:
            continue
        key = (_surname(guest.guest_name), guest.arrival_date, guest.departure_date)
        surname_key_to_records.setdefault(key, []).append(guest)

    for records in surname_key_to_records.values():
        # Require at least two DISTINCT first names -- if it's the same
        # guest_name repeated, that's already an exact_name group (or a
        # true duplicate record), not a same-surname case.
        distinct_names = {r.guest_name.strip().lower() for r in records}
        if len(records) > 1 and len(distinct_names) > 1:
            groups.append(RoomGroup(guest_name=records[0].guest_name, records=records, matched_by="same_surname"))

    return groups


def group_for_guest(
    guest: GuestRecord, groups_by_confirmation: dict[str, RoomGroup]
) -> list[GuestRecord]:
    group = groups_by_confirmation.get(guest.confirmation_number)
    if group is None:
        return []
    return [r for r in group.records if r.confirmation_number != guest.confirmation_number]
