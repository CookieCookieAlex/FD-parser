"""Parser for the guest-arrivals PDF ("Arrivals with Details").

This is not a table -- it's a label-anchored form, one variable-length block
per guest. See CLAUDE.md for the full structure notes. Strategy:

1. Extract words per page with pdfplumber, keep (x0, x1, top, bottom, text)
   (rows.py).
2. Group words into rows by `top` (words on the same printed line share a
   `top` within a small tolerance) (rows.py).
3. Drop boilerplate rows -- the repeated page header/footer/column-header
   text that appears on every page at (roughly) the same `top` bands
   (rows.py).
4. Walk the remaining rows. A row is a new-record anchor when it has a
   `Reserved` (or other status word) in the status column and an
   MM/DD/YYYY date in the arrival-date column. Everything between one
   anchor and the next belongs to that guest's record.
5. Within a record: the row right after the anchor carries room type,
   confirmation number, and departure date. Subsequent rows are either
   `Stay Date (Days)` rows (skipped -- redundant with arrival/departure)
   or right-aligned label/value rows (`VIP Level:`, `Address:`,
   `Guest Notes:`, etc.) whose label sits in a narrow column ending
   around x1=158 and whose value starts around x0=163 (record_builder.py).
6. State (current record, current label being continued) carries across
   page boundaries, since notes can span a page break with no new anchor.
"""
from __future__ import annotations

import re

import pdfplumber

from fd_reader.models import GuestRecord
from fd_reader.parse_guests.record_builder import RecordBuilder, match_label
from fd_reader.parse_guests.rows import (
    LABEL_VALUE_BOUNDARY,
    Row,
    extract_rows,
    is_boilerplate,
    is_record_anchor,
    is_stay_date_row,
)

__all__ = ["parse_guest_pdf", "GuestRecord"]


def _consume_row(row: Row, row_text: str, builder: RecordBuilder) -> None:
    """Apply one non-anchor, non-boilerplate row to the in-progress
    record: a label/value row, a continuation line of the active
    multi-line field, or (if neither) an unrecognized-row warning."""
    if is_stay_date_row(row):
        return

    label_match = match_label(row)
    if label_match:
        field, value = label_match
        builder.consume_label_row(field, value)
        return

    left_text = row.text_in_range(x0=None, x1=LABEL_VALUE_BOUNDARY).strip()
    if not left_text and builder.active_field:
        value = row.text_in_range(x0=LABEL_VALUE_BOUNDARY).strip()
        builder.append_field_text(builder.active_field, value)
        return

    if not left_text:
        return

    builder.warnings.append(f"unrecognized_row:{row_text[:80]!r}")


def parse_guest_pdf(path: str) -> list[GuestRecord]:
    records: list[GuestRecord] = []
    builder: RecordBuilder | None = None
    expect_detail_row = False
    reported_total: int | None = None

    with pdfplumber.open(path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            rows = extract_rows(page)
            for row in rows:
                text = row.text_in_range()
                if not text.strip():
                    continue

                total_match = re.search(r"Total Reservations\s+(\d+)", text)
                if total_match:
                    reported_total = int(total_match.group(1))

                if is_boilerplate(row):
                    continue

                anchor = is_record_anchor(row)
                if anchor:
                    if builder is not None:
                        records.append(builder.finalize())
                    status, arrival_date = anchor
                    builder = RecordBuilder(status, arrival_date, page_index)
                    builder.consume_anchor_row(row)
                    expect_detail_row = True
                    continue

                if builder is None:
                    continue

                if expect_detail_row:
                    builder.consume_detail_row(row)
                    expect_detail_row = False
                    continue

                _consume_row(row, text, builder)

    if builder is not None:
        records.append(builder.finalize())

    if reported_total is not None and reported_total != len(records):
        for r in records:
            r.flags.append(
                f"count_mismatch: parsed {len(records)} vs report total {reported_total}"
            )

    return records
