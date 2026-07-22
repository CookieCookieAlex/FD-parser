"""Small, reusable Streamlit UI pieces with no guest/reservation-specific
knowledge -- the collapse toggle and pagination bar are used by card.py
and main.py but don't depend on GuestBlock shapes themselves.
"""
from __future__ import annotations

import streamlit as st

_CIRCLE_TOGGLE_CSS = """
<style>
.st-key-{key} button {{
    border-radius: 50%;
    border: 1px solid rgba(91, 140, 255, 0.35) !important;
    background-color: rgba(91, 140, 255, 0.10) !important;
    padding: 0 !important;
    width: 2.7em;
    height: 2.7em;
    min-width: 2.7em;
    min-height: 2.7em;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.15s ease, box-shadow 0.15s ease;
}}
.st-key-{key} button div,
.st-key-{key} button span,
.st-key-{key} button p {{
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    width: 100%;
    height: 100%;
    font-weight: 700;
    font-size: 1.2em;
    color: rgb(91, 140, 255);
}}
.st-key-{key} button:hover {{
    background-color: rgba(91, 140, 255, 0.22) !important;
    box-shadow: 0 0 0 1px rgba(91, 140, 255, 0.5);
}}
</style>
"""


def circle_toggle_button(state_key: str, default_collapsed: bool = False) -> bool:
    """Small circle button (⌄ open / ⌃ closed); returns True while
    collapsed. Starts at `default_collapsed` (e.g. pre-collapsed for
    Matched cards, so staff only expand the ones worth a second look),
    remembered per state_key across reruns after that."""
    toggle_key = f"toggle-{state_key}"
    st.html(_CIRCLE_TOGGLE_CSS.format(key=toggle_key))

    collapsed_key = f"collapsed-{state_key}"
    if collapsed_key not in st.session_state:
        st.session_state[collapsed_key] = default_collapsed

    with st.container(key=toggle_key):
        arrow = "⌃" if st.session_state[collapsed_key] else "⌄"
        if st.button(arrow, key=f"{toggle_key}-btn", type="tertiary", width="content"):
            st.session_state[collapsed_key] = not st.session_state[collapsed_key]
            st.rerun(scope="fragment")

    return st.session_state[collapsed_key]


_PAGINATION_BUTTON_CSS = """
<style>
.st-key-{key} button {{
    font-size: 19px !important;
    padding: 7px 15px !important;
}}
</style>
"""


def pagination_controls(total_pages: int, key_suffix: str) -> None:
    """Prev/Next + page indicator. Two of these share the same
    st.session_state["_page_number"] (top and bottom of the page), so a
    click forces one extra st.rerun() -- cheap, no PDF work -- to keep
    both bars' enabled-state and label in sync immediately instead of one
    lagging a click behind."""
    row_key = f"pagination-row-{key_suffix}"
    st.html(_PAGINATION_BUTTON_CSS.format(key=row_key))
    with st.container(key=row_key):
        prev_col, label_col, next_col = st.columns([0.15, 0.7, 0.15], vertical_alignment="center")
        current_page = st.session_state.get("_page_number", 1)
        with prev_col:
            if st.button("◂ Prev", key=f"page-prev-{key_suffix}", disabled=current_page <= 1, width="stretch"):
                st.session_state["_page_number"] = current_page - 1
                st.rerun()
        with next_col:
            if st.button(
                "Next ▸", key=f"page-next-{key_suffix}", disabled=current_page >= total_pages, width="stretch"
            ):
                st.session_state["_page_number"] = current_page + 1
                st.rerun()
        with label_col:
            st.markdown(
                f"<div style='text-align:center;'>Page {current_page} of {total_pages}</div>",
                unsafe_allow_html=True,
            )
