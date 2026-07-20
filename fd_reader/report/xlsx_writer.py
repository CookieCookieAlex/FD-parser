"""Render GuestBlocks (blocks.py) to a color-coded .xlsx file.

Two side-by-side column groups per block:
  - LEFT (guest-list side): label/value pairs, then the three raw note
    fields, wrapped.
  - RIGHT (Yelp side): one line per ReservationLine, colored per
    colors.py, with a short status note and the raw Notes & Tags text.
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from fd_reader.report.blocks import GuestBlock
from fd_reader.report.colors import BLOCK_BORDER_FILL, BLUE, GREEN, ORANGE, RED, YELLOW

_FONT_HEADER = Font(bold=True, color="FFFFFF")
_FONT_LABEL = Font(bold=True)
_FONT_TITLE = Font(bold=True, size=12)
_WRAP = Alignment(wrap_text=True, vertical="top")

LEFT_COL_COUNT = 9  # label + value pairs render across these columns
RIGHT_START_COL = LEFT_COL_COUNT + 2  # one blank spacer column
RIGHT_COL_COUNT = 6

_LEFT_FIELDS = [
    ("Confirmation #", "confirmation_number"),
    ("Room", "room_name"),
    ("Room Type", "room_type"),
    ("Arrival", "arrival_date"),
    ("Departure", "departure_date"),
    ("Guests", "guests_count"),
    ("Rate Plan", "rate_plan"),
]

_LEFT_NOTE_FIELDS = [
    ("Guest Notes", "guest_notes"),
    ("Reservation Notes", "reservation_notes"),
    ("Comments / Notes", "comments_notes"),
]


def write_report(
    blocks: list[GuestBlock],
    path: str,
    room_move_count: int = 0,
    group_booking_count: int = 0,
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Guest x Yelp Cross-Check"

    _write_summary(
        sheet, blocks, row=1,
        room_move_count=room_move_count,
        group_booking_count=group_booking_count,
    )
    row = 4
    row = _write_legend(sheet, row)
    row += 1

    for block in blocks:
        row = _write_block(sheet, block, row)
        row += 1  # blank row between blocks

    _set_column_widths(sheet)
    workbook.save(path)


def _write_summary(
    sheet: Worksheet,
    blocks: list[GuestBlock],
    row: int,
    room_move_count: int = 0,
    group_booking_count: int = 0,
) -> None:
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
        f"{color_counts[RED]} mismatched, {color_counts[BLUE]} no reservation, "
        f"{room_move_count} room move{'s' if room_move_count != 1 else ''}, "
        f"{group_booking_count} group booking{'s' if group_booking_count != 1 else ''}"
    ))


def _write_legend(sheet: Worksheet, row: int) -> int:
    legend = [
        (GREEN, "Matched cleanly"),
        (YELLOW, "Needs a look (missing mention, room/party mismatch, unresolved note)"),
        (RED, "Mismatch (note and Yelp disagree on restaurant/date/room)"),
        (BLUE, "No Yelp reservation and no note mention"),
        (ORANGE, "Perk badge (Virtuoso / breakfast included)"),
    ]
    for i, (color, label) in enumerate(legend):
        col = 1 + i * 2
        cell = sheet.cell(row=row, column=col, value="  ")
        cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        sheet.cell(row=row, column=col + 1, value=label)
    return row + 1


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

    perk_labels = []
    if block.virtuoso:
        perk_labels.append("Virtuoso")
    if block.breakfast_included:
        perk_labels.append("Breakfast included")
    for label in perk_labels:
        color_cell = sheet.cell(row=right_row, column=right_col, value="  ")
        color_cell.fill = PatternFill(start_color=ORANGE, end_color=ORANGE, fill_type="solid")
        sheet.cell(row=right_row, column=right_col + 1, value=label)
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
