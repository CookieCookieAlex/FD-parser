"""Guest-card rendering: the main per-guest card (info + matched Yelp
reservations) and the top summary bar of counts.
"""
from __future__ import annotations

import streamlit as st

from fd_reader.app_ui.content import (
    COLOR_BADGE,
    COLOR_LABEL,
    COLOR_STRIPE,
    FIELD_LABEL_STYLE,
    FIELD_VALUE_STYLE,
    LEFT_FIELD_ROWS,
    NOTE_FIELDS,
    NOTE_TEXT_STYLE,
    THIN_DIVIDER,
)
from fd_reader.app_ui.formatting import block_worst_color, display_room, format_time_12h, nights_stayed
from fd_reader.app_ui.widgets import circle_toggle_button
from fd_reader.report import BLUE, GREEN, GuestBlock, RED, YELLOW


_COLLAPSED_CARD_CSS = """
<style>
.st-key-{card_key} {{ padding-bottom: 0.4rem !important; }}
.st-key-{card_key} h4 {{ margin-bottom: 0.1rem !important; }}
</style>
"""

# Status color as a left-edge stripe on the whole card, so which cards
# need attention reads from peripheral vision on a scroll past, not just
# from reading each badge in turn. Applied every render (not just when
# collapsed) via the card's own container key.
_STRIPE_CSS = """
<style>
.st-key-{card_key} {{ border-left: 4px solid {stripe_color} !important; }}
</style>
"""

# Guest name bumped up from the default h4 size (~1rem) to 1.48rem -- the
# name is the card's primary key, it should read from further away than a
# field label, not blend in with body text. (+5px/+0.3rem on top of the
# earlier 1.18rem bump, per user request to size up all card text.)
_NAME_CSS = """
<style>
.st-key-{key} h4 {{ font-size: 1.48rem !important; }}
</style>
"""

# The header badge is the card's one headline verdict, so it gets a solid
# fill; per-reservation-line badges are supporting detail underneath it and
# stay as lighter outline chips -- st.badge() itself has no "solid vs
# outline" param, so both are plain CSS overrides scoped by container key.
_HEADER_BADGE_CSS = """
<style>
.st-key-{key} .stMarkdownBadge {{
    font-weight: 700 !important;
}}
</style>
"""
_LINE_BADGE_CSS = """
<style>
.st-key-{key} .stMarkdownBadge {{
    background-color: transparent !important;
    box-shadow: inset 0 0 0 1px currentColor;
    font-weight: 600 !important;
}}
</style>
"""


def _field_row(pairs: list[tuple[str, object]]) -> None:
    """Render a row of (label, value) pairs as quiet-label/bold-value HTML
    pairs across even columns -- replaces the old
    `**Label:**  \\n value` markdown, which rendered label and value at
    the same size/weight so a scanning eye had to read the label to find
    the answer.

    Every pair gets its own column even when the value is missing (shown
    as "None") -- dropping empty ones used to collapse the column count,
    which shifted every field after the gap into the wrong visual slot
    (e.g. "Yelp Guest" sliding under the "Time" header when "Room" was
    blank)."""
    if not pairs:
        return
    for col, (label, value) in zip(st.columns(len(pairs)), pairs):
        display_value = value if value not in (None, "") else "None"
        col.markdown(
            f"<div style='{FIELD_LABEL_STYLE}'>{label}</div>"
            f"<div style='{FIELD_VALUE_STYLE}'>{display_value}</div>",
            unsafe_allow_html=True,
        )


def _card_bar(container_key: str, state_key: str, guest_name: str, worst: str, block: GuestBlock) -> bool:
    """Main card bar: guest name + status badge on the left (with small
    room-move/group-booking icons still visible when collapsed), and a
    circle expand/collapse arrow on the right. Returns True if collapsed.
    A collapsed card also gets its header padding/type tightened (via
    _COLLAPSED_CARD_CSS) so minimizing a long guest list actually shortens
    the page, not just hides the body."""
    st.html(_STRIPE_CSS.format(card_key=container_key, stripe_color=COLOR_STRIPE[worst]))
    st.html(_NAME_CSS.format(key=container_key))

    title_col, button_col = st.columns([0.918, 0.082], vertical_alignment="center")
    with title_col:
        icons = ""
        if block.room_move_note:
            icons += " 🔁"
        if block.linked_group_note:
            icons += " 🔗"
        st.markdown(f"#### {guest_name}{icons}")
        badge_key = f"header-badge-{state_key}"
        with st.container(key=badge_key):
            st.html(_HEADER_BADGE_CSS.format(key=badge_key))
            st.badge(COLOR_LABEL[worst], color=COLOR_BADGE[worst])
    with button_col:
        # Matched cards start collapsed -- they're the everyday case with
        # nothing to check, so staff only expand one to double-check it
        # rather than scrolling past a full expanded card for every guest.
        collapsed = circle_toggle_button(state_key, default_collapsed=(worst == GREEN))
    if collapsed:
        st.html(_COLLAPSED_CARD_CSS.format(card_key=container_key))
    return collapsed


@st.fragment
def render_card(block: GuestBlock, index: int) -> None:
    guest = block.guest
    worst = block_worst_color(block)
    # index is always unique per render (it's each block's position in the
    # filtered/paginated list), unlike confirmation_number -- pipeline.py's
    # _split_duplicate_confirmations pulls duplicate-confirmation-number
    # guests out of matching, but their placeholder cards can still land in
    # the same render as each other, so card_key must not rely on
    # confirmation_number being unique (Streamlit requires every
    # widget/container key to be unique across the whole page, not just
    # within one card).
    card_key = f"{guest.confirmation_number or 'noconf'}-{index}"

    card_container_key = f"guest-card-{index}"
    with st.container(border=True, key=card_container_key):
        card_collapsed = _card_bar(card_container_key, f"card-{card_key}", guest.guest_name, worst, block)

        if card_collapsed:
            return

        if block.duplicate_id_note:
            st.error(block.duplicate_id_note, icon="⚠️")
        if block.room_move_note:
            st.info(block.room_move_note, icon="🔁")
        if block.linked_group_note:
            st.info(block.linked_group_note, icon="🔗")
        # Capacity alert sits with the other banners, directly under the
        # header -- previously it rendered at the bottom of the left
        # column, after the notes, where a fast scroll past could miss
        # the single loudest signal on the card.
        if block.capacity_note:
            st.error(block.capacity_note, icon="🚨")
        if block.sofa_bed_alert:
            st.error(block.sofa_bed_alert, icon="🛋️")

        body_container = st.container(key=f"body-cols-{card_key}")
        with body_container:
            left, right = st.columns(2, border=True)

        with left:
            st.markdown("**Guest Info**")
            _field_row([("Confirmation #", guest.confirmation_number)])
            for field_row in LEFT_FIELD_ROWS:
                _field_row([(label, getattr(guest, attr)) for label, attr in field_row])

            nights = nights_stayed(guest)
            if nights:
                _field_row([("Nights", nights)])

            has_perks = (
                block.virtuoso or block.breakfast_included or block.pet_amenities or block.sofa_bed_requested
            )
            if has_perks:
                with st.container(horizontal=True):
                    if block.virtuoso:
                        st.badge("Virtuoso", color="orange")
                    if block.breakfast_included:
                        st.badge("Breakfast included", color="orange")
                    if block.pet_amenities:
                        st.badge("Pet amenities", color="orange")
                    if block.sofa_bed_requested:
                        st.badge("Sofa bed requested", color="orange")

            has_notes = any(getattr(guest, attr) for _, attr in NOTE_FIELDS)
            if has_perks and has_notes:
                st.markdown(THIN_DIVIDER, unsafe_allow_html=True)

            for label, attr in NOTE_FIELDS:
                value = getattr(guest, attr)
                if value:
                    st.markdown(f"<div style='{FIELD_LABEL_STYLE}'>{label}</div>", unsafe_allow_html=True)
                    st.markdown(
                        f"<div style='{NOTE_TEXT_STYLE}'>{value}</div>",
                        unsafe_allow_html=True,
                    )

        with right:
            st.markdown("**Yelp Reservations**")
            for line_index, line in enumerate(block.lines):
                if line_index > 0:
                    st.markdown(THIN_DIVIDER, unsafe_allow_html=True)
                label = COLOR_LABEL[line.color]
                if len(block.lines) > 1:
                    label = f"{label} ({line_index + 1}/{len(block.lines)})"
                r = line.reservation

                if r is not None:
                    room = display_room(r)
                    detail_fields = [
                        ("Date", r.source_date),
                        ("Time", format_time_12h(r.time)),
                        ("Party of", r.party_size),
                        ("Restaurant", r.restaurant or "(unclear)"),
                        ("Room", room),
                        ("Yelp Guest", r.guest_name or "(none)"),
                    ]
                else:
                    detail_fields = []

                badge_col, arrow_col = st.columns([0.85, 0.15], vertical_alignment="center")
                with badge_col:
                    line_badge_key = f"line-badge-{card_key}-{line_index}"
                    with st.container(key=line_badge_key):
                        st.html(_LINE_BADGE_CSS.format(key=line_badge_key))
                        st.badge(label, color=COLOR_BADGE[line.color])
                with arrow_col:
                    line_collapsed = circle_toggle_button(f"yelp-line-{card_key}-{line_index}")

                if line_collapsed:
                    continue

                st.markdown(
                    f"<div style='{NOTE_TEXT_STYLE}'>{line.note}</div>",
                    unsafe_allow_html=True,
                )

                if detail_fields:
                    for row_start in range(0, len(detail_fields), 3):
                        row = detail_fields[row_start : row_start + 3]
                        _field_row(row)
                    if r.notes_tags:
                        st.markdown(
                            f"<div style='{FIELD_LABEL_STYLE}'>Notes & Tags</div>", unsafe_allow_html=True
                        )
                        st.markdown(
                            f"<div style='{NOTE_TEXT_STYLE}'>{r.notes_tags}</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("(no reservation)")


# Summary metrics ("Total guests" / colored counts) bumped +5px/+0.3rem
# on top of Streamlit's default metric sizing (14px label -> 19px, 36px
# value -> 41px), same "starting part" text-size pass as the header CSS
# in main.py -- st.metric has no font-size param, so this is scoped CSS
# on the summary bar's own container key.
_SUMMARY_METRIC_CSS = """
<style>
.st-key-summary-bar [data-testid="stMetricLabel"] p { font-size: 1.1875rem !important; }
.st-key-summary-bar [data-testid="stMetricValue"] { font-size: 2.5625rem !important; }
</style>
"""


def summary_bar(blocks: list[GuestBlock], room_move_count: int, group_booking_count: int) -> None:
    counts = {GREEN: 0, YELLOW: 0, RED: 0, BLUE: 0}
    for block in blocks:
        counts[block_worst_color(block)] += 1

    st.html(_SUMMARY_METRIC_CSS)
    with st.container(key="summary-bar"):
        cols = st.columns(7)
        cols[0].metric("Total guests", len(blocks))
        cols[1].metric("🟢 Clean", counts[GREEN])
        cols[2].metric("🟡 Needs a look", counts[YELLOW])
        cols[3].metric("🔴 Mismatched", counts[RED])
        cols[4].metric("🔵 No reservation", counts[BLUE])
        cols[5].metric("🔁 Room moves", room_move_count)
        cols[6].metric("🔗 Group bookings", group_booking_count)
