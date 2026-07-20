"""Assemble one GuestBlock per guest -- the shared shape consumed by both
the xlsx writer (xlsx_writer.py) and the Streamlit app (fd_reader/app.py),
so card logic and spreadsheet logic can't drift apart.

Layout, per user direction: one visual BLOCK per guest (every guest, full
roster, arrival-date order) -- not a flat spreadsheet row. Each block pairs:

  - the guest-list side: confirmation ID, room, room type, arrival,
    departure, guest count, and all three raw note fields (Guest Notes /
    Reservation Notes / Comments-Notes) -- always shown in full, even when
    there's nothing to flag, so staff can eyeball the original note next
    to what the tool found.
  - the Yelp side: one ReservationLine per matched reservation (date, time,
    party size, guest name, Notes & Tags), OR a single placeholder line if
    the guest has no Yelp reservation at all.

Each Yelp-side line gets its own color + short note (not one blended color
per guest, since a guest can have several reservations with mixed results
and blending would hide a real problem) -- see colors.py for what each
color means.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fd_reader.match import MatchResult, NoteCrossCheck, RoomMove, find_room_groups
from fd_reader.models import GuestRecord
from fd_reader.parse_reservations import ReservationRecord
from fd_reader.report.colors import BLUE, GREEN, RED, YELLOW


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


def _sorted_by_arrival(guests: list[GuestRecord]) -> list[GuestRecord]:
    def key(g: GuestRecord):
        try:
            return datetime.strptime(g.arrival_date.strip(), "%m/%d/%Y")
        except (ValueError, AttributeError):
            return datetime.max

    return sorted(guests, key=key)


def _line_status(
    result: MatchResult, related_checks: list[NoteCrossCheck]
) -> tuple[str, str]:
    mismatch_checks = [c for c in related_checks if c.status == "mismatch"]
    matched_checks = [c for c in related_checks if c.status == "matched"]
    without_note_checks = [c for c in related_checks if c.status == "reservation_without_note"]

    if mismatch_checks:
        return RED, mismatch_checks[0].detail

    notes: list[str] = []
    color = GREEN

    if "room_mismatch" in result.flags:
        color = YELLOW
        notes.append("Room in Yelp note disagrees with guest's actual room.")
    if "party_size_mismatch" in result.flags:
        color = YELLOW
        notes.append(
            f"Party size mismatch (Yelp: {result.reservation.party_size}, "
            f"guest list: {result.guest.guests_count})."
        )
    if without_note_checks and not matched_checks:
        color = YELLOW
        notes.append("Reservation found in Yelp but not mentioned in any guest note field.")

    if not notes:
        notes.append("Matched cleanly.")

    return color, " ".join(notes)


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

    # Note mentions that never resolved to any Yelp reservation at all
    # (no MatchResult exists for them) -- e.g. Guest H's ambiguous
    # Maggie's mention with nothing to disambiguate against.
    for check in unresolved_checks:
        lines.append(
            ReservationLine(
                color=YELLOW,
                note=f"Note mentions {check.mention.restaurant} but no matching Yelp reservation found ({check.detail}).",
                reservation=None,
            )
        )

    return lines


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
    guests: list[GuestRecord],
) -> dict[str, tuple[list[tuple[str, str | None]], str]]:
    """Computed once so every block in a group gets the pointer note, not
    just the record that happened to hold the matched reservation (see
    find_room_groups' docstring -- e.g. Guest B's 3 rooms). The
    reservation itself still only ever shows on its own confirmation ID's
    block; this is purely a "look at the sibling room" pointer.
    (room_name, other_guest_name_or_None) -- the guest name is only
    included for same_surname groups, where the other room belongs to a
    DIFFERENT person (e.g. "Guest Y"), not shown for exact_name groups
    where it'd just repeat this guest's own name."""
    result: dict[str, tuple[list[tuple[str, str | None]], str]] = {}
    for group in find_room_groups(guests):
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
) -> list[GuestBlock]:
    """Assemble one GuestBlock per guest, arrival-date order."""
    results_by_guest: dict[str, list[MatchResult]] = {}
    for result in match_results:
        if result.guest is not None:
            results_by_guest.setdefault(result.guest.confirmation_number, []).append(result)

    checks_by_guest: dict[str, list[NoteCrossCheck]] = {}
    for check in note_checks:
        checks_by_guest.setdefault(check.guest.confirmation_number, []).append(check)

    moved_from: dict[str, RoomMove] = {}
    moved_to: dict[str, RoomMove] = {}
    for move in room_moves:
        moved_from[move.earlier.confirmation_number] = move
        moved_to[move.later.confirmation_number] = move

    group_rooms_by_confirmation = _group_rooms_by_confirmation(guests)

    blocks: list[GuestBlock] = []

    for guest in _sorted_by_arrival(guests):
        guest_results = results_by_guest.get(guest.confirmation_number, [])
        guest_checks = checks_by_guest.get(guest.confirmation_number, [])

        lines = _build_lines(guest_results, guest_checks)
        if not lines:
            lines = [ReservationLine(color=BLUE, note="No Yelp reservation and no note mention.")]

        blocks.append(
            GuestBlock(
                guest=guest,
                lines=lines,
                room_move_note=_room_move_note(guest, moved_from, moved_to),
                linked_group_note=_linked_group_note(guest, group_rooms_by_confirmation),
            )
        )

    return blocks
