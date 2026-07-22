"""Pure display-formatting helpers for guest cards -- no Streamlit calls,
so these are testable without a running app.
"""
from __future__ import annotations

import re
from datetime import datetime

from fd_reader.report import GuestBlock, worst_color
from fd_reader.rooms.aliases import resolve_room_code_hint


def format_time_12h(time_text: str) -> str:
    """Yelp reservation times are parsed as bare `H:MM` -- dinner service
    only, so every one of them is PM. Pass through unrecognized text as-is."""
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_text.strip())
    if not match:
        return time_text
    return f"{match.group(1)}:{match.group(2)} PM"


def nights_stayed(guest) -> str:
    """Departure minus arrival (standard hotel convention: Mon->Wed is 2
    nights, not 3). Returns "" if either date is missing/unparseable."""
    try:
        arrival = datetime.strptime(guest.arrival_date.strip(), "%m/%d/%Y")
        departure = datetime.strptime(guest.departure_date.strip(), "%m/%d/%Y")
    except (ValueError, AttributeError):
        return ""
    nights = (departure - arrival).days
    return str(nights) if nights >= 0 else ""


def display_room(r) -> str:
    """Room-code hint text as shown on a reservation card. Prefer the
    resolved PMS room name; fall back to the raw Notes & Tags leftover
    with its stray leading/trailing "'s"/"S " noise (left behind by the
    restaurant-keyword strip in parse_reservations.py) trimmed off --
    if that noise was the ENTIRE hint (e.g. "artisans" -> "s"), the
    result is empty, meaning there's genuinely no room hint left to show."""
    if r.is_outside_guest:
        return "Outside guest"
    room = resolve_room_code_hint(r.room_code_hint)
    if room is not None:
        return room.abbreviation or room.full_name
    if r.room_code_hint:
        return re.sub(r"^['\s,.\-]*s\b[\s,.\-]*", "", r.room_code_hint, flags=re.IGNORECASE).strip()
    return ""


def block_worst_color(block: GuestBlock) -> str:
    return worst_color(line.color for line in block.lines)
