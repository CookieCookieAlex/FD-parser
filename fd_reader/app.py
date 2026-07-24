"""Streamlit GUI entry point: `streamlit run` and the PyInstaller build
(see server_entry.py) both need this as a real, directly-runnable file,
so it stays a thin script -- the actual implementation lives in the
fd_reader.app_ui package (see its __init__.py docstring for the module
breakdown).

Run with:
    streamlit run fd_reader/app.py
"""
from __future__ import annotations

import os
import sys

# `streamlit run` executes this file directly, so the project root isn't
# on sys.path -- add it before any fd_reader import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fd_reader.app_ui import (
    _load_from_uploads,
    _mtime_fingerprint,
    _run_pipeline,
    configure_page,
    main,
)

configure_page()
main()
