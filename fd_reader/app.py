"""Streamlit GUI: browser-based guest-card viewer.

Runs the full pipeline itself (parse -> match -> cross-check -> build
blocks) from either a folder path or uploaded PDFs -- no separate CLI
step needed. This is an alternative VIEW of the same data the .xlsx
report shows (fd_reader/report.py); it does not replace the Excel export,
which is still useful for sharing/archiving a week's results as a static
file. Both consume the same `GuestBlock`/`ReservationLine` shape from
report.py, so card logic and spreadsheet logic can't drift apart.

Run with:
    streamlit run fd_reader/app.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# `streamlit run fd_reader/app.py` executes this file directly rather than
# as part of the fd_reader package, so the project root isn't on sys.path
# and `import fd_reader.*` fails with ModuleNotFoundError. Add it before
# any fd_reader import, so `streamlit run fd_reader/app.py` works from the
# project root with no extra PYTHONPATH setup required.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from fd_reader.cli import _discover_pdfs
from fd_reader.match import (
    cross_check_notes,
    detect_room_moves,
    find_room_groups,
    match_reservations,
)
from fd_reader.parse_guests import parse_guest_pdf
from fd_reader.parse_reservations import parse_reservation_pdf
from fd_reader.report import BLUE, GREEN, RED, YELLOW, GuestBlock, build_guest_blocks

st.set_page_config(page_title="Guest x Yelp Cross-Check", layout="wide")

_COLOR_HEX = {GREEN: "#C6EFCE", YELLOW: "#FFEB9C", RED: "#FFC7CE", BLUE: "#BDD7EE"}
_COLOR_LABEL = {GREEN: "Matched", YELLOW: "Needs a look", RED: "Mismatch", BLUE: "No reservation"}
_COLOR_TEXT = {GREEN: "#0F5132", YELLOW: "#664D03", RED: "#842029", BLUE: "#084298"}

_LEFT_FIELDS = [
    ("Room", "room_name"),
    ("Room Type", "room_type"),
    ("Arrival", "arrival_date"),
    ("Departure", "departure_date"),
    ("Guests", "guests_count"),
]

_NOTE_FIELDS = [
    ("Guest Notes", "guest_notes"),
    ("Reservation Notes", "reservation_notes"),
    ("Comments / Notes", "comments_notes"),
]


@st.cache_data(show_spinner=False)
def _run_pipeline(
    guest_paths: tuple[str, ...], yelp_paths: tuple[str, ...]
) -> tuple[list[GuestBlock], int, int]:
    guests = []
    for path in guest_paths:
        guests.extend(parse_guest_pdf(path))

    reservations = []
    for path in yelp_paths:
        reservations.extend(parse_reservation_pdf(path))

    match_results = match_reservations(guests, reservations)
    note_checks = cross_check_notes(guests, match_results)
    room_moves = detect_room_moves(guests)
    room_groups = find_room_groups(guests)

    blocks = build_guest_blocks(guests, match_results, note_checks, room_moves)
    return blocks, len(room_moves), len(room_groups)


def _block_worst_color(block: GuestBlock) -> str:
    severity = {RED: 3, YELLOW: 2, BLUE: 1, GREEN: 0}
    colors = [line.color for line in block.lines]
    return max(colors, key=lambda c: severity[c]) if colors else BLUE


def _render_card(block: GuestBlock) -> None:
    guest = block.guest
    worst = _block_worst_color(block)
    border_color = _COLOR_HEX[worst]

    with st.container(border=True):
        st.markdown(
            f"<div style='border-left:6px solid {border_color}; padding-left:12px;'>"
            f"<h4 style='margin:0'>{guest.guest_name}</h4>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if block.room_move_note:
            st.info(block.room_move_note, icon="🔁")
        if block.linked_group_note:
            st.info(block.linked_group_note, icon="🔗")

        left, right = st.columns(2)

        with left:
            st.markdown("**Guest Info**")
            st.caption(f"Confirmation # {guest.confirmation_number}")
            for label, attr in _LEFT_FIELDS:
                value = getattr(guest, attr)
                if value not in (None, ""):
                    st.markdown(f"**{label}:** {value}")
            for label, attr in _NOTE_FIELDS:
                value = getattr(guest, attr)
                if value:
                    with st.expander(label):
                        st.text(value)

        with right:
            st.markdown("**Yelp Reservations**")
            for line in block.lines:
                hex_color = _COLOR_HEX[line.color]
                text_color = _COLOR_TEXT[line.color]
                label = _COLOR_LABEL[line.color]

                if line.reservation is not None:
                    r = line.reservation
                    summary = (
                        f"{r.restaurant or '(restaurant unclear)'} — "
                        f"{r.source_date} {r.time} — party of {r.party_size} — {r.guest_name}"
                    )
                else:
                    summary = "(no reservation)"

                st.markdown(
                    f"<div style='background:{hex_color}; color:{text_color}; "
                    f"padding:8px 12px; border-radius:6px; margin-bottom:6px;'>"
                    f"<b>{label}</b> — {summary}<br>"
                    f"<span style='font-size:0.9em'>{line.note}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if line.reservation is not None and line.reservation.notes_tags:
                    st.caption(f"Notes & Tags: {line.reservation.notes_tags}")


def _summary_bar(blocks: list[GuestBlock], room_move_count: int, group_booking_count: int) -> None:
    counts = {GREEN: 0, YELLOW: 0, RED: 0, BLUE: 0}
    for block in blocks:
        counts[_block_worst_color(block)] += 1

    cols = st.columns(7)
    cols[0].metric("Total guests", len(blocks))
    cols[1].metric("🟢 Clean", counts[GREEN])
    cols[2].metric("🟡 Needs a look", counts[YELLOW])
    cols[3].metric("🔴 Mismatched", counts[RED])
    cols[4].metric("🔵 No reservation", counts[BLUE])
    cols[5].metric("🔁 Room moves", room_move_count)
    cols[6].metric("🔗 Group bookings", group_booking_count)


def _load_from_folder(folder: str) -> tuple[list[GuestBlock], int, int] | None:
    if not folder or not os.path.isdir(folder):
        st.warning("Enter a valid folder path.")
        return None
    guest_paths, yelp_paths = _discover_pdfs(folder)
    if not guest_paths:
        st.error("No arrivals-report PDF found in that folder (looked for 'Arrivals with Details').")
        return None
    if not yelp_paths:
        st.error("No Yelp reservation PDFs found in that folder.")
        return None
    return _run_pipeline(tuple(guest_paths), tuple(yelp_paths))


def _load_from_uploads(uploaded_files) -> tuple[list[GuestBlock], int, int] | None:
    if not uploaded_files:
        return None

    tmp_dir = tempfile.mkdtemp(prefix="fd_reader_upload_")
    for uploaded in uploaded_files:
        with open(os.path.join(tmp_dir, uploaded.name), "wb") as f:
            f.write(uploaded.getbuffer())

    guest_paths, yelp_paths = _discover_pdfs(tmp_dir)
    if not guest_paths:
        st.error("No arrivals-report PDF found among the uploaded files.")
        return None
    if not yelp_paths:
        st.error("No Yelp reservation PDFs found among the uploaded files.")
        return None
    return _run_pipeline(tuple(guest_paths), tuple(yelp_paths))


def main() -> None:
    st.title("Guest × Yelp Reservation Cross-Check")
    st.caption(
        "One card per guest — room/dates/notes on the left, matched Yelp "
        "reservations on the right. 🟢 matched · 🟡 needs a look · "
        "🔴 mismatch · 🔵 no reservation."
    )

    mode = st.radio("Load PDFs from:", ["Folder path", "Upload files"], horizontal=True)

    result: tuple[list[GuestBlock], int, int] | None = None
    if mode == "Folder path":
        folder = st.text_input("Folder containing the arrivals PDF(s) and Yelp PDF(s)")
        if st.button("Load", type="primary") and folder:
            with st.spinner("Parsing and matching..."):
                result = _load_from_folder(folder)
            st.session_state["result"] = result
    else:
        uploaded = st.file_uploader(
            "Upload the arrivals PDF(s) and Yelp PDF(s)", type="pdf", accept_multiple_files=True
        )
        if st.button("Load", type="primary") and uploaded:
            with st.spinner("Parsing and matching..."):
                result = _load_from_uploads(uploaded)
            st.session_state["result"] = result

    result = st.session_state.get("result")
    if not result:
        return
    blocks, room_move_count, group_booking_count = result

    _summary_bar(blocks, room_move_count, group_booking_count)
    st.divider()

    filter_choice = st.multiselect(
        "Show only:",
        options=[GREEN, YELLOW, RED, BLUE],
        default=[GREEN, YELLOW, RED, BLUE],
        format_func=lambda c: _COLOR_LABEL[c],
    )
    search = st.text_input("Search guest name")

    for block in blocks:
        if _block_worst_color(block) not in filter_choice:
            continue
        if search and search.lower() not in block.guest.guest_name.lower():
            continue
        _render_card(block)


main()
