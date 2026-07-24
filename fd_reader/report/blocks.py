"""Assemble one GuestBlock per guest -- the shared shape consumed by both
the xlsx writer (xlsx_writer.py) and the Streamlit app (fd_reader/app.py),
so card logic and spreadsheet logic can't drift apart.

One block per guest (full roster, arrival-date order), pairing:
  - the guest-list side: confirmation ID, room, dates, guest count, and
    all three raw note fields, always shown in full.
  - the Yelp side: one ReservationLine per matched reservation, or a
    placeholder line if there's no Yelp reservation at all.

Each Yelp-side line gets its own color + note (not one blended color per
guest, since mixed results on one guest would otherwise hide a real
problem) -- see colors.py for what each color means.

Also shown: perk badges (Virtuoso / breakfast-included / pet amenities,
match/perks.py) in ORANGE since they're informational, not match-status;
an optional RED over-capacity warning (match/capacity_check.py) when
guests_count exceeds the room's max_guests; and an optional sofa-bed
signal (match/sofa_bed_check.py) when a note field requests one --
ORANGE "Sofa bed requested" badge if the assigned room has one, RED alert
if it doesn't (a real staff action item, likely needs a room move).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fd_reader.match._dates import parse_mmddyyyy
from fd_reader.match import (
    MatchResult,
    NoteCrossCheck,
    RoomGroup,
    RoomMove,
    check_capacity,
    check_sofa_bed,
    find_room_groups,
    is_breakfast_included,
    is_pet_amenities,
    is_virtuoso,
)
from fd_reader.models import GuestRecord
from fd_reader.parsing.reservations import ReservationRecord
from fd_reader.report.colors import BLUE, GREEN, RED, YELLOW
from fd_reader.util import group_by


@dataclass
class ReservationLine:
    """One right-column line inside a guest's block: a Yelp reservation
    (or lack thereof) plus the color/note summarizing its status."""
    color: str
    note: str
    reservation: ReservationRecord | None = None


@dataclass
class GuestBlock:
    guest: GuestRecord
    lines: list[ReservationLine]
    room_move_note: str | None = None
    linked_group_note: str | None = None
    virtuoso: bool = False
    breakfast_included: bool = False
    pet_amenities: bool = False
    capacity_note: str | None = None
    # True when a note field requests a sofa bed AND the assigned room has
    # one -- shown as an informational badge alongside virtuoso/breakfast/
    # pet_amenities above. When requested but the room does NOT have one,
    # this stays False and sofa_bed_alert (below) is set instead -- the two
    # are mutually exclusive by construction (see _sofa_bed_signals).
    sofa_bed_requested: bool = False
    sofa_bed_alert: str | None = None
    # Only ever set by app_ui/pipeline.py (not by build_guest_blocks below,
    # and not read by the .xlsx writer) -- see pipeline.py's
    # _flag_duplicate_confirmation_numbers for why this needs to live on
    # the Streamlit-app side rather than here.
    duplicate_id_note: str | None = None


def _sorted_by_arrival(guests: list[GuestRecord]) -> list[GuestRecord]:
    def key(g: GuestRecord):
        return parse_mmddyyyy(g.arrival_date) or datetime.max.date()

    return sorted(guests, key=key)


def _line_status(
    result: MatchResult, related_checks: list[NoteCrossCheck]
) -> tuple[str, str]:
    mismatch_checks = [c for c in related_checks if c.status in ("mismatch", "time_mismatch")]
    matched_checks = [c for c in related_checks if c.status == "matched"]
    without_note_checks = [c for c in related_checks if c.status == "reservation_without_note"]

    if mismatch_checks:
        return RED, mismatch_checks[0].detail

    if "surname_only_no_room_hint" in result.flags:
        return RED, (
            "Potential outside guest: matched by last name only, no first name or "
            "room found in the Yelp notes -- could be a different person who "
            "happens to share this guest's last name. Please verify."
        )

    if "ambiguous_name_match" in result.flags:
        other_names = ", ".join(g.guest_name for g in result.other_candidates)
        return RED, (
            f"Ambiguous match: could also belong to {other_names} (same/similar name, "
            f"also in-house that night, no room hint or note time to tell them apart). "
            f"Attached here as the closest name match -- please verify."
        )

    notes: list[str] = []
    color = GREEN

    if "resolved_by_note_time" in result.flags:
        other_names = ", ".join(g.guest_name for g in result.other_candidates)
        color = YELLOW
        notes.append(
            f"Name match was ambiguous ({other_names} also plausible), resolved using "
            f"a matching time in this guest's notes -- please verify."
        )

    if "room_mismatch" in result.flags:
        color = YELLOW
        notes.append("Room in Yelp note disagrees with guest's actual room.")
    if "no_room_hint" in result.flags:
        color = YELLOW
        notes.append("No room found in the Yelp notes for this reservation.")
    if "party_size_mismatch" in result.flags:
        color = YELLOW
        notes.append(
            f"Party size mismatch (Yelp: {result.reservation.party_size}, "
            f"guest list: {result.guest.guests_count})."
        )
    if without_note_checks and not matched_checks:
        color = YELLOW
        notes.append("Reservation found in Yelp but not mentioned in Guest Notes.")

    if not notes:
        notes.append("Matched cleanly.")

    return color, "\n".join(notes)


def _build_lines(
    guest_results: list[MatchResult], guest_checks: list[NoteCrossCheck]
) -> list[ReservationLine]:
    checks_by_reservation: dict[int, list[NoteCrossCheck]] = {}
    unresolved_checks: list[NoteCrossCheck] = []
    for check in guest_checks:
        if check.reservation is not None:
            checks_by_reservation.setdefault(id(check.reservation), []).append(check)
        elif check.mention is not None:
            unresolved_checks.append(check)

    lines: list[ReservationLine] = []

    for result in guest_results:
        reservation = result.reservation
        related_checks = checks_by_reservation.get(id(reservation), [])
        color, note = _line_status(result, related_checks)
        lines.append(ReservationLine(color=color, note=note, reservation=reservation))

    # Note mentions that never resolved to any Yelp reservation at all.
    for check in unresolved_checks:
        note = f"Guest Notes mentions {check.mention.restaurant} but no matching Yelp reservation found."
        if check.detail:
            note = f"{note[:-1]} ({check.detail})."
        lines.append(ReservationLine(color=YELLOW, note=note, reservation=None))

    return lines


def _capacity_note(guest: GuestRecord) -> str | None:
    check = check_capacity(guest)
    if check is None:
        return None
    return (
        f"Guest count exceeds room capacity: {check.actual_guests} guests booked, "
        f"but {guest.room_name} sleeps {check.max_guests} max."
    )


def _sofa_bed_signals(guest: GuestRecord) -> tuple[bool, str | None]:
    """(sofa_bed_requested, sofa_bed_alert) -- mutually exclusive: a
    satisfied request sets the first, an unsatisfied one sets the second,
    no request found leaves both False/None."""
    check = check_sofa_bed(guest)
    if check is None:
        return False, None
    if check.satisfied:
        return True, None
    return False, (
        f"Sofa bed requested but {guest.room_name} doesn't have one -- "
        f"likely needs a room move before arrival."
    )


def _room_move_note(guest: GuestRecord, moved_from: dict, moved_to: dict) -> str | None:
    if guest.confirmation_number in moved_from:
        move = moved_from[guest.confirmation_number]
        return f"Room move: {move.earlier.room_name} -> {move.later.room_name} on {move.later.arrival_date}"
    if guest.confirmation_number in moved_to:
        move = moved_to[guest.confirmation_number]
        return f"Room move: moved here from {move.earlier.room_name} on {guest.arrival_date}"
    return None


def _linked_group_note(
    guest: GuestRecord,
    group_rooms_by_confirmation: dict[str, tuple[list[tuple[str, str | None]], str]],
) -> str | None:
    group_entry = group_rooms_by_confirmation.get(guest.confirmation_number)
    if not group_entry or not group_entry[0]:
        return None

    other_rooms, matched_by = group_entry
    if matched_by == "same_surname":
        room_descriptions = ", ".join(
            f"{room} ({other_name})" if other_name else room
            for room, other_name in other_rooms
        )
        return (
            f"Probable group booking (same surname, same dates, different "
            f"first name) -- also see room(s): {room_descriptions}"
        )

    room_descriptions = ", ".join(room for room, _ in other_rooms)
    return f"Linked group booking (same name/dates) -- also see room(s): {room_descriptions}"


def _group_rooms_by_confirmation(
    groups: list[RoomGroup],
) -> dict[str, tuple[list[tuple[str, str | None]], str]]:
    """Computed once so every block in a group gets the "look at the
    sibling room" pointer note, not just the record holding the matched
    reservation. (room_name, other_guest_name_or_None) -- the guest name
    is only included for same_surname groups, where the other room
    belongs to a different person; omitted for exact_name groups where
    it'd just repeat this guest's own name."""
    result: dict[str, tuple[list[tuple[str, str | None]], str]] = {}
    for group in groups:
        for record in group.records:
            other_rooms = [
                (
                    r.room_name,
                    r.guest_name if group.matched_by == "same_surname" else None,
                )
                for r in group.records
                if r.confirmation_number != record.confirmation_number and r.room_name
            ]
            result[record.confirmation_number] = (other_rooms, group.matched_by)
    return result


def build_guest_blocks(
    guests: list[GuestRecord],
    match_results: list[MatchResult],
    note_checks: list[NoteCrossCheck],
    room_moves: list[RoomMove],
    groups: list[RoomGroup] | None = None,
) -> list[GuestBlock]:
    """Assemble one GuestBlock per guest, arrival-date order.

    `groups` lets a caller that's already computed find_room_groups(guests)
    (e.g. for match_reservations or a group-booking count) pass it in
    instead of recomputing it here."""
    if groups is None:
        groups = find_room_groups(guests)

    results_by_guest = group_by(
        (r for r in match_results if r.guest is not None),
        lambda r: r.guest.confirmation_number,
    )
    checks_by_guest = group_by(note_checks, lambda c: c.guest.confirmation_number)

    moved_from: dict[str, RoomMove] = {}
    moved_to: dict[str, RoomMove] = {}
    for move in room_moves:
        moved_from[move.earlier.confirmation_number] = move
        moved_to[move.later.confirmation_number] = move

    group_rooms_by_confirmation = _group_rooms_by_confirmation(groups)

    blocks: list[GuestBlock] = []

    for guest in _sorted_by_arrival(guests):
        guest_results = results_by_guest.get(guest.confirmation_number, [])
        guest_checks = checks_by_guest.get(guest.confirmation_number, [])

        lines = _build_lines(guest_results, guest_checks)
        if not lines:
            lines = [ReservationLine(color=BLUE, note="No Yelp reservation and no note mention.")]

        sofa_bed_requested, sofa_bed_alert = _sofa_bed_signals(guest)

        blocks.append(
            GuestBlock(
                guest=guest,
                lines=lines,
                room_move_note=_room_move_note(guest, moved_from, moved_to),
                linked_group_note=_linked_group_note(guest, group_rooms_by_confirmation),
                virtuoso=is_virtuoso(guest),
                breakfast_included=is_breakfast_included(guest),
                pet_amenities=is_pet_amenities(guest),
                capacity_note=_capacity_note(guest),
                sofa_bed_requested=sofa_bed_requested,
                sofa_bed_alert=sofa_bed_alert,
            )
        )

    return blocks
