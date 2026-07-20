"""Build the color-coded guest <-> Yelp cross-check report.

blocks.py assembles one GuestBlock per guest (shared by both output
surfaces); xlsx_writer.py renders those blocks to a .xlsx file. The
Streamlit app (fd_reader/app.py) renders the same blocks as cards instead,
so card logic and spreadsheet logic can't drift apart.
"""
from __future__ import annotations

from fd_reader.report.blocks import GuestBlock, ReservationLine, build_guest_blocks
from fd_reader.report.colors import BLOCK_BORDER_FILL, BLUE, GREEN, HEADER_FILL, RED, YELLOW
from fd_reader.report.xlsx_writer import write_report

__all__ = [
    "GuestBlock",
    "ReservationLine",
    "build_guest_blocks",
    "BLOCK_BORDER_FILL",
    "BLUE",
    "GREEN",
    "HEADER_FILL",
    "RED",
    "YELLOW",
    "write_report",
]
