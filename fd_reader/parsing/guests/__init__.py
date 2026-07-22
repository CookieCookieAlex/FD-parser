"""Parser for the guest-arrivals PDF ("Arrivals with Details").

Not a table -- a label-anchored form, one variable-length block per guest.
rows.py extracts/groups words into rows and drops boilerplate; a row is a
new-record anchor when it has a status word and an MM/DD/YYYY arrival date.
record_builder.py accumulates everything between one anchor and the next
into a GuestRecord, including state that carries across page breaks.
"""
from __future__ import annotations

import re

import pdfplumber

from fd_reader.models import GuestRecord
from fd_reader.parsing.guests.record_builder import RecordBuilder, match_label
from fd_reader.parsing.guests.rows import (
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
