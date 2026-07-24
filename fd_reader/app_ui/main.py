"""Page wiring: header, load controls (folder path / upload), and the
filtered + paginated card list. Imports every other app_ui submodule.
"""
from __future__ import annotations

import streamlit as st

from fd_reader.app_ui.card import render_card, summary_bar
from fd_reader.app_ui.content import COLOR_LABEL, HOW_TO_USE_ABOUT, HOW_TO_USE_IMPORTANT, HOW_TO_USE_START, PAGE_SIZE
from fd_reader.app_ui.formatting import block_worst_color
from fd_reader.app_ui.pipeline import _load_from_folder, _load_from_uploads
from fd_reader.app_ui.widgets import pagination_controls
from fd_reader.report import BLUE, GREEN, RED, YELLOW, severity_rank

_SORT_ARRIVAL = "Arrival time"
_SORT_SEVERITY = "Status severity"
_SORT_NAME = "Guest name (A–Z)"
_SORT_OPTIONS = [_SORT_ARRIVAL, _SORT_SEVERITY, _SORT_NAME]

# "Starting part" of the page -- title through the caption -- bumped +5px/
# +0.3rem per user request, same as the card text sizes earlier. st.title/
# st.caption have no font-size param, so this is scoped CSS on the title
# container's own key, same pattern as the card's badge/toggle overrides.
_HEADER_TEXT_CSS = """
<style>
.st-key-header-block h1 { font-size: 2.8625rem !important; }
/* Lowered back down from the earlier +5px bump (1.5525rem) -- at that
   size the caption wrapped to two lines and ran off the right edge on a
   normal window width. 1.05rem keeps it comfortably above the original
   Streamlit default (~1rem) while fitting on one line. */
.st-key-header-block [data-testid="stCaptionContainer"] p { font-size: 1.05rem !important; }
</style>
"""

# Load / Upload / Info / Clear buttons bumped +3px (16px -> 19px font,
# padding scaled up to match so the button box grows with the text
# instead of the text just overflowing its old box). st.button has no
# font-size param, so this targets each button's own container key --
# NOT a blanket button[kind=...] selector, since that would also catch
# the pagination Prev/Next buttons (widgets.py), which stay their
# current size.
_BIG_BUTTON_CSS = """
<style>
.st-key-info-popover-trigger button,
.st-key-load-clear-row button,
[data-testid="stFileUploaderDropzone"] button {
    font-size: 19px !important;
    padding: 7px 15px !important;
}
</style>
"""

# "Sort by" (selectbox) label + selected-option text bumped up a bit --
# not part of the "starting part" +5px pass or the +3px button pass, just
# a smaller standalone bump per user follow-up.
_FILTER_SORT_CSS = """
<style>
.st-key-filter-sort-row label p { font-size: 17px !important; }
.st-key-filter-sort-row [data-baseweb="select"] * { font-size: 16px !important; }
</style>
"""


def main() -> None:
    st.html(_HEADER_TEXT_CSS)
    st.html(_BIG_BUTTON_CSS)
    st.html(_FILTER_SORT_CSS)
    title_col, info_col = st.columns([6, 1])
    with title_col:
        with st.container(key="header-block"):
            st.title("Guest + Yelp Reservation Cross-Check")
            st.caption(
                "One card per guest — room/dates/notes on the left, matched Yelp "
                "reservations on the right. 🟢 matched · 🟡 needs a look · "
                "🔴 mismatch · 🔵 no reservation."
            )
    with info_col:
        with st.popover("ℹ️ Info", key="info-popover-trigger"):
            tab_important, tab_about, tab_start = st.tabs(
                ["Important", "About", "How to start"]
            )
            with tab_important:
                st.markdown(HOW_TO_USE_IMPORTANT)
            with tab_about:
                st.markdown(HOW_TO_USE_ABOUT)
            with tab_start:
                st.markdown(HOW_TO_USE_START)

    mode = st.radio("Load PDFs from:", ["Upload files", "Folder path"], horizontal=True)

    if mode == "Upload files":
        uploader_key = f"uploader-{st.session_state.get('_uploader_generation', 0)}"
        uploaded = st.file_uploader(
            "Upload the arrivals PDF(s) and Yelp PDF(s)", type="pdf", accept_multiple_files=True,
            key=uploader_key,
        )
        with st.container(horizontal=True, key="load-clear-row"):
            load_clicked = st.button("Load", type="primary", width="content")
            # Bumping the widget's key remounts st.file_uploader as a
            # fresh, empty widget -- there's no other API to clear an
            # already-selected file list from code.
            if st.button("Clear uploaded files", width="content"):
                st.session_state["_uploader_generation"] = (
                    st.session_state.get("_uploader_generation", 0) + 1
                )
                st.rerun()
        if load_clicked and uploaded:
            with st.spinner("Parsing and matching..."):
                result = _load_from_uploads(uploaded)
            if result is not None:
                st.session_state["result"] = result
    else:
        folder_key = f"folder-{st.session_state.get('_folder_generation', 0)}"
        folder = st.text_input(
            "Folder containing the arrivals PDF(s) and Yelp PDF(s)", key=folder_key,
        )
        with st.container(horizontal=True, key="load-clear-row"):
            load_clicked = st.button("Load", type="primary", width="content")
            # Bumping the widget's key remounts st.text_input as a fresh,
            # empty widget -- same approach as the uploader's clear button
            # above, there's no other API to clear a widget's value from
            # code once the user has typed into it.
            if st.button("Clear folder path", width="content"):
                st.session_state["_folder_generation"] = (
                    st.session_state.get("_folder_generation", 0) + 1
                )
                st.rerun()
        if load_clicked and folder:
            with st.spinner("Parsing and matching..."):
                result = _load_from_folder(folder)
            # Only overwrite a previously-loaded result on success -- a
            # failed reload (bad path, missing PDFs) must not wipe out
            # cards that were already showing from an earlier good load.
            if result is not None:
                st.session_state["result"] = result

    result = st.session_state.get("result")
    if not result:
        return
    blocks, room_move_count, group_booking_count = result

    summary_bar(blocks, room_move_count, group_booking_count)
    st.divider()

    with st.container(key="filter-sort-row"):
        # Individual toggle pills instead of a multiselect dropdown -- each
        # status is its own on/off button (red outline = shown, gray =
        # hidden), so there's no dropdown to open and no "clear all" (x)
        # to misclick, unlike the multiselect this replaced.
        filter_choice = st.pills(
            "Show only:",
            options=[GREEN, YELLOW, RED, BLUE],
            selection_mode="multi",
            default=[GREEN, YELLOW, RED, BLUE],
            format_func=lambda c: COLOR_LABEL[c],
        ) or []
        # Search only ever holds a short guest name -- a fixed narrow width
        # instead of stretching the full row width like every other control.
        # Sort by sits directly under it, same narrow column, not sharing a
        # row -- both are "narrow, secondary" controls next to the wide
        # Show only pill row above.
        search = st.text_input("Search guest name", width=260)
        sort_choice = st.selectbox("Sort by:", options=_SORT_OPTIONS, width=260)

    filtered = [
        (index, block)
        for index, block in enumerate(blocks)
        if block_worst_color(block) in filter_choice
        and (not search or search.lower() in block.guest.guest_name.lower())
    ]

    # Arrival time is blocks' own existing order (report/blocks.py sorts
    # guests by arrival before building blocks), so that case is a no-op.
    # Severity sorts worst-first (RED > YELLOW > BLUE > GREEN), pairing
    # naturally with the status stripe -- sorted worst-first, the red
    # stripes cluster at the top of the page.
    if sort_choice == _SORT_SEVERITY:
        filtered.sort(key=lambda item: severity_rank(block_worst_color(item[1])), reverse=True)
    elif sort_choice == _SORT_NAME:
        filtered.sort(key=lambda item: item[1].guest.guest_name.lower())

    # Reset to page 1 when the filter/search/sort changes, so a stale page
    # number can't point past the end of a smaller result set.
    filter_signature = (tuple(filter_choice), search, sort_choice)
    if st.session_state.get("_page_filter_signature") != filter_signature:
        st.session_state["_page_filter_signature"] = filter_signature
        st.session_state["_page_number"] = 1

    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    st.session_state["_page_number"] = min(st.session_state.get("_page_number", 1), total_pages)

    pagination_controls(total_pages, key_suffix="top")

    if not filtered:
        if search:
            st.info(f"No guest found matching \"{search}\".")
        else:
            st.info("No guests match the selected filters.")
        return

    page_number = st.session_state["_page_number"]
    start = (page_number - 1) * PAGE_SIZE
    page_items = filtered[start : start + PAGE_SIZE]

    for index, block in page_items:
        render_card(block, index)

    if page_items:
        pagination_controls(total_pages, key_suffix="bottom")
