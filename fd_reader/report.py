"""Build the color-coded guest <-> Yelp cross-check report.

Layout, per user direction: one visual BLOCK per guest (every guest, full
roster, arrival-date order) -- not a flat spreadsheet row. Each block is
two side-by-side column groups:

  - LEFT (guest-list side): confirmation ID, room, room type, arrival,
    departure, guest count, and all three raw note fields (Guest Notes /
    Reservation Notes / Comments-Notes) -- always shown in full, even when
    there's nothing to flag, so staff can eyeball the original note next
    to what the tool found.
  - RIGHT (Yelp side): one line per matched reservation (date, time, party
    size, guest name, Notes & Tags), OR a single placeholder line if the
    guest has no Yelp reservation at all.

Each Yelp-side line gets its own color + short note (not one blended
color per guest, since a guest can have several reservations with mixed
results and blending would hide a real problem):

  - GREEN  -- matched cleanly, nothing to flag.
  - YELLOW -- a soft/incomplete issue: a reservation Yelp has that no note
    mentions, an ambiguous weekday note that couldn't be resolved, a
    party-size mismatch, or a room-code hint that disagrees with the
    guest's actual room (room_mismatch) -- something worth a glance, not
    a hard conflict.
  - RED    -- a hard conflict: both sides have data but they disagree
    (the note names a different restaurant, or a different date, than
    what's actually booked in Yelp -- fd_reader.match's "mismatch" status).
  - BLUE   -- nothing to compare at all: no Yelp reservation AND no note
    mention. Not a problem by itself, just informational.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from fd_reader.match import MatchResult, NoteCrossCheck, RoomMove, find_room_groups
from fd_reader.models import GuestRecord
from fd_reader.parse_reservations import ReservationRecord

GREEN = "C6EFCE"
YELLOW = "FFEB9C"
RED = "FFC7CE"
BLUE = "BDD7EE"
HEADER_FILL = "44546A"
BLOCK_BORDER_FILL = "D9D9D9"

_FONT_HEADER = Font(bold=True, color="FFFFFF")
_FONT_LABEL = Font(bold=True)
_FONT_TITLE = Font(bold=True, size=12)
_WRAP = Alignment(wrap_text=True, vertical="top")


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


def _by_confirmation(guests: list[GuestRecord]) -> dict[str, GuestRecord]:
    return {g.confirmation_number: g for g in guests}


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

    # Computed once so every block in a group gets the pointer note, not
    # just the record that happened to hold the matched reservation (see
    # find_room_groups' docstring -- e.g. Guest B's 3 rooms). The
    # reservation itself still only ever shows on its own confirmation
    # ID's block; this is purely a "look at the sibling room" pointer.
    group_rooms_by_confirmation: dict[str, list[str]] = {}
    for group in find_room_groups(guests):
        for record in group.records:
            other_rooms = [
                r.room_name for r in group.records
                if r.confirmation_number != record.confirmation_number and r.room_name
            ]
            group_rooms_by_confirmation[record.confirmation_number] = other_rooms

    blocks: list[GuestBlock] = []

    for guest in _sorted_by_arrival(guests):
        guest_results = results_by_guest.get(guest.confirmation_number, [])
        guest_checks = checks_by_guest.get(guest.confirmation_number, [])

        lines = _build_lines(guest_results, guest_checks)
        if not lines:
            lines = [ReservationLine(color=BLUE, note="No Yelp reservation and no note mention.")]

        room_move_note = None
        if guest.confirmation_number in moved_from:
            move = moved_from[guest.confirmation_number]
            room_move_note = f"Room move: {move.earlier.room_name} -> {move.later.room_name} on {move.later.arrival_date}"
        elif guest.confirmation_number in moved_to:
            move = moved_to[guest.confirmation_number]
            room_move_note = f"Room move: moved here from {move.earlier.room_name} on {guest.arrival_date}"

        linked_group_note = None
        other_rooms = group_rooms_by_confirmation.get(guest.confirmation_number)
        if other_rooms:
            linked_group_note = (
                f"Linked group booking (same name/dates) -- also see room(s): "
                f"{', '.join(other_rooms)}"
            )

        blocks.append(
            GuestBlock(
                guest=guest,
                lines=lines,
                room_move_note=room_move_note,
                linked_group_note=linked_group_note,
            )
        )

    return blocks


def _sorted_by_arrival(guests: list[GuestRecord]) -> list[GuestRecord]:
    def key(g: GuestRecord):
        try:
            return datetime.strptime(g.arrival_date.strip(), "%m/%d/%Y")
        except (ValueError, AttributeError):
            return datetime.max

    return sorted(guests, key=key)


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


# --- openpyxl rendering -----------------------------------------------

LEFT_COL_COUNT = 9  # label + value pairs render across these columns
RIGHT_START_COL = LEFT_COL_COUNT + 2  # one blank spacer column
RIGHT_COL_COUNT = 6


def write_report(blocks: list[GuestBlock], path: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Guest x Yelp Cross-Check"

    _write_summary(sheet, blocks, row=1)
    row = 4
    row = _write_legend(sheet, row)
    row += 1

    for block in blocks:
        row = _write_block(sheet, block, row)
        row += 1  # blank row between blocks

    _set_column_widths(sheet)
    workbook.save(path)


def _write_summary(sheet: Worksheet, blocks: list[GuestBlock], row: int) -> None:
    total = len(blocks)
    color_counts = {GREEN: 0, YELLOW: 0, RED: 0, BLUE: 0}
    for block in blocks:
        colors = {line.color for line in block.lines}
        for color in (RED, YELLOW, BLUE, GREEN):
            if color in colors:
                color_counts[color] += 1
                break

    sheet.cell(row=row, column=1, value="Guest x Yelp Reservation Cross-Check").font = _FONT_TITLE
    sheet.cell(row=row + 1, column=1, value=(
        f"{total} guests -- "
        f"{color_counts[GREEN]} clean, {color_counts[YELLOW]} need a look, "
        f"{color_counts[RED]} mismatched, {color_counts[BLUE]} no reservation"
    ))


def _write_legend(sheet: Worksheet, row: int) -> int:
    legend = [
        (GREEN, "Matched cleanly"),
        (YELLOW, "Needs a look (missing mention, room/party mismatch, unresolved note)"),
        (RED, "Mismatch (note and Yelp disagree on restaurant/date/room)"),
        (BLUE, "No Yelp reservation and no note mention"),
    ]
    for i, (color, label) in enumerate(legend):
        col = 1 + i * 2
        cell = sheet.cell(row=row, column=col, value="  ")
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        sheet.cell(row=row, column=col + 1, value=label)
    return row + 1


_LEFT_FIELDS = [
    ("Confirmation #", "confirmation_number"),
    ("Room", "room_name"),
    ("Room Type", "room_type"),
    ("Arrival", "arrival_date"),
    ("Departure", "departure_date"),
    ("Guests", "guests_count"),
]

_LEFT_NOTE_FIELDS = [
    ("Guest Notes", "guest_notes"),
    ("Reservation Notes", "reservation_notes"),
    ("Comments / Notes", "comments_notes"),
]


def _write_block(sheet: Worksheet, block: GuestBlock, row: int) -> int:
    guest = block.guest
    start_row = row

    title_cell = sheet.cell(row=row, column=1, value=guest.guest_name)
    title_cell.font = _FONT_TITLE
    row += 1

    if block.room_move_note:
        sheet.cell(row=row, column=1, value=block.room_move_note).font = Font(italic=True)
        row += 1
    if block.linked_group_note:
        sheet.cell(row=row, column=1, value=block.linked_group_note).font = Font(italic=True)
        row += 1

    field_row = row
    for label, attr in _LEFT_FIELDS:
        sheet.cell(row=field_row, column=1, value=label).font = _FONT_LABEL
        sheet.cell(row=field_row, column=2, value=str(getattr(guest, attr) or ""))
        field_row += 1

    for label, attr in _LEFT_NOTE_FIELDS:
        sheet.cell(row=field_row, column=1, value=label).font = _FONT_LABEL
        cell = sheet.cell(row=field_row, column=2, value=getattr(guest, attr) or "")
        cell.alignment = _WRAP
        field_row += 1

    right_row = row
    right_col = RIGHT_START_COL
    sheet.cell(row=right_row, column=right_col, value="Yelp Reservations").font = _FONT_LABEL
    right_row += 1

    for line in block.lines:
        color_cell = sheet.cell(row=right_row, column=right_col, value="  ")
        color_cell.fill = PatternFill(start_color=line.color, end_color=line.color, fill_type="solid")

        if line.reservation is not None:
            r = line.reservation
            summary = (
                f"{r.restaurant or '(restaurant unclear)'} -- {r.source_date} {r.time} -- "
                f"party of {r.party_size} -- {r.guest_name}"
            )
        else:
            summary = "(no reservation)"

        sheet.cell(row=right_row, column=right_col + 1, value=summary)
        note_cell = sheet.cell(row=right_row, column=right_col + 2, value=line.note)
        note_cell.alignment = _WRAP
        right_row += 1

        if line.reservation is not None and line.reservation.notes_tags:
            sheet.cell(
                row=right_row, column=right_col + 1,
                value=f"Notes & Tags: {line.reservation.notes_tags}",
            ).alignment = _WRAP
            right_row += 1

    end_row = max(field_row, right_row) - 1
    row = end_row + 1

    for r in range(start_row, row + 1):
        sheet.cell(row=r, column=LEFT_COL_COUNT + 1).fill = PatternFill(
            start_color=BLOCK_BORDER_FILL, end_color=BLOCK_BORDER_FILL, fill_type="solid"
        )

    return row


def _set_column_widths(sheet: Worksheet) -> None:
    widths = {1: 22, 2: 45, RIGHT_START_COL: 3, RIGHT_START_COL + 1: 45, RIGHT_START_COL + 2: 40}
    for col, width in widths.items():
        sheet.column_dimensions[get_column_letter(col)].width = width
