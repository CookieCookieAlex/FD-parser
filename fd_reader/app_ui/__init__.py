"""Streamlit GUI internals, split out of the top-level fd_reader/app.py
entry script (which `streamlit run` and the PyInstaller build both need
as a literal runnable file, so it can't itself be this package).

content.py    - static text/color/label constants
formatting.py - pure display-formatting helpers
pipeline.py   - parse/match/cache pipeline, folder + upload loaders
widgets.py    - generic reusable UI pieces (collapse toggle, pagination)
card.py       - guest-card rendering + summary bar
main.py       - page layout wiring, calls into all of the above

An alternative VIEW of the same data the .xlsx report shows -- doesn't
replace the Excel export, which is still useful for sharing/archiving.
Both consume the same `GuestBlock`/`ReservationLine` shape from report.py.
"""
from __future__ import annotations

import streamlit as st

from fd_reader.app_ui.formatting import block_worst_color
from fd_reader.app_ui.main import main
from fd_reader.app_ui.pipeline import _load_from_uploads, _mtime_fingerprint, _run_pipeline

__all__ = [
    "main",
    "block_worst_color",
    "_load_from_uploads",
    "_mtime_fingerprint",
    "_run_pipeline",
]


def configure_page() -> None:
    st.set_page_config(page_title="Guest + Yelp Cross-Check", layout="wide")
    st.html(
        """
        <style>
        [class*='st-key-guest-card-'] { background-color: #17181B; }
        [class*='st-key-body-cols-'] [data-testid='stColumn'] { background-color: #23262B; }
        </style>
        """
    )
