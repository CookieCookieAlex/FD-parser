"""Status colors shared by the block-building logic (blocks.py), the xlsx
writer (xlsx_writer.py), and the Streamlit app (fd_reader/app.py).

  - GREEN  -- matched cleanly, nothing to flag.
  - YELLOW -- a soft/incomplete issue: a reservation Yelp has that no note
    mentions, an ambiguous weekday note that couldn't be resolved, a
    party-size mismatch, or a room-code hint that disagrees with the
    guest's actual room (room_mismatch) -- something worth a glance, not
    a hard conflict.
  - RED    -- a hard conflict: both sides have data but they disagree
    (the note names a different restaurant, or a different date, than
    what's actually booked in Yelp -- fd_reader.match's "mismatch" status).
  - BLUE   -- nothing to compare at all: no Yelp reservation AND no note
    mention. Not a problem by itself, just informational.
  - ORANGE -- not a match-status color at all: used only for the perk
    badges (Virtuoso / breakfast-included) detected from the guest's note
    text. Informational, shown alongside the Yelp reservation lines.
"""
from __future__ import annotations

GREEN = "C6EFCE"
YELLOW = "FFEB9C"
RED = "FFC7CE"
BLUE = "BDD7EE"
ORANGE = "FCD5B4"
HEADER_FILL = "44546A"
BLOCK_BORDER_FILL = "D9D9D9"
