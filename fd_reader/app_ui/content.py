"""Static text/lookup constants for the Streamlit app: color labels/badges,
field layouts, and the "Info" popover copy. No logic, no Streamlit calls.
"""
from __future__ import annotations

from fd_reader.report import BLUE, GREEN, RED, YELLOW

# Card/status colors come from Streamlit's theming system
# (.streamlit/config.toml [theme], dark-only) except the guest-card
# background set in app.py's st.html() call, which needs its own shade
# with no config.toml slot for it. Keep these hex values in sync with
# config.toml if it changes.
COLOR_LABEL = {GREEN: "Matched", YELLOW: "Needs a look", RED: "Mismatch", BLUE: "No reservation"}
# Only ever looked up by a ReservationLine/block color (GREEN/YELLOW/RED/
# BLUE) -- perk badges (Virtuoso/Breakfast/Pet amenities) are a separate
# rendering path that hardcodes color="orange" directly, so ORANGE never
# needs an entry here.
COLOR_BADGE = {GREEN: "green", YELLOW: "yellow", RED: "red", BLUE: "blue"}
# Card-edge status stripe -- same 4 hues as COLOR_BADGE, as raw hex so
# they can go straight into a CSS border-left instead of through
# st.badge()'s named-color palette.
COLOR_STRIPE = {GREEN: "#4ADE80", YELLOW: "#FBBF24", RED: "#F87171", BLUE: "#60A5FA"}

LEFT_FIELD_ROWS = [
    [("Room", "room_name"), ("Room Type", "room_type"), ("Rate Plan", "rate_plan")],
    [("Arrival", "arrival_date"), ("Departure", "departure_date"), ("Guests", "guests_count")],
]

# Display order + labels for the three GuestRecord note fields (see
# models.NOTE_FIELDS for the plain field-name tuple these attrs come from).
NOTE_FIELD_LABELS = [
    ("Guest Notes", "guest_notes"),
    ("Reservation Notes", "reservation_notes"),
    ("Comments / Notes", "comments_notes"),
]

# Bounds the worst-case redraw cost per rerun regardless of full list size
# (see card.py's render_card, an @st.fragment).
PAGE_SIZE = 10

# Shared style for free-text note blocks (guest notes + Yelp Notes & Tags)
# so they read as one consistent size/font. Sized to MATCH field values
# (1.22rem, same as FIELD_VALUE_STYLE below) rather than smaller -- free
# text is what staff actually have to read (e.g. "Artisans 7/10 @ 7PM"),
# while structured fields like "Room: PINE" only need to be scanned, so
# shrinking exactly the text that needs reading was backwards. All four
# card text sizes (name, note, label, value) were bumped +5px/+0.3rem
# uniformly per user request -- ratios between them unchanged.
NOTE_TEXT_STYLE = "font-size:1.22rem; color:#eceef0; line-height:1.5; white-space:pre-wrap; margin:2px 0 10px 0;"

# Quiet uppercase label / bold value pair, used everywhere a "Label: value"
# used to be a single bold "**Label:**  \n value" markdown line -- the
# label is now the quiet part and the value is the loud part, so a
# scanning eye lands on the answer instead of the question.
FIELD_LABEL_STYLE = (
    "font-size:0.98rem; font-weight:700; text-transform:uppercase; "
    "letter-spacing:0.03em; color:#8a8f98; margin:0;"
)
FIELD_VALUE_STYLE = "font-size:1.22rem; font-weight:700; color:#f5f6f7; margin:1px 0 0;"

# st.divider()'s built-in margin is too thick for use between sections
# inside a column, so this is a plain <hr> with a small margin instead.
THIN_DIVIDER = "<hr style='margin:6px 0; border:none; border-top:1px solid rgba(128,128,128,0.3);'>"

HOW_TO_USE_IMPORTANT = """
⚠️ **This is a helper tool, not a replacement for reading the reports yourself.**

- It's built to catch things faster — it can still get things wrong or break.
- Always double-check anything flagged 🔴 or 🟡 against the real PDFs before acting on it.
- Don't rely on it as the single source of truth. Manual read-through is still essential.
"""

HOW_TO_USE_ABOUT = """
**What this does:** compares the hotel's arrival list against the Yelp for
dinner reservations, so you don't have to manually check both lists against
each other.

It also shows you the Virtuoso and Breakfast Included notes, pulled from the guest notes.

It gives you quick info about the guest: arrival, departure, rate, room
type, room name, confirmation ID, and guest count per room.

It shows you if the guest is moving rooms — by checking if the room type
or name changes during their stay, or if the departure and arrival dates
match up under the same guest name.

It also shows you if a guest is part of a group booking.

**What to expect:** one card per guest, color-coded 🟢 matched · 🟡 needs a
look · 🔴 mismatch · 🔵 no reservation, each with a short note underneath
explaining what was found.
A faster way to spot what the notes might have
missed, not a final verdict.
"""

HOW_TO_USE_START = """
### A. Make a folder where you will save PDF's

1. Go to Dekstop and press right click and make a folder.
   Name it as you like.
2. Do not change the name of the files — it will not work if you rename them.

### B. Get the arrival notes (HMS)

1. In HMS, open the ☰ burger menu → search **"Advance Arrival with Details"**.
2. Scroll down and set:
   - **Sort by:** Arrival Date
   - **End date:** 7 days out from today
   - ⚠️ Don't set it further than 7 days — the report comes back as a blank PDF.
      If that happens, pull the end date back one day at a time until it shows data.
3. Click **Print** / **Show** at the top of HMS — it opens as a PDF.
4. `Ctrl + S` to save it into a folder you've made for this.

### C. Get the Yelp reservations (one day at a time)

1. Go to Yelp for Business reservations.
2. Yelp only exports **one day per PDF** — open each day in the *same* 7-day range as the arrival notes, one at a time.
3. `Ctrl + S` each day's PDF into the **same folder** as the arrival notes.
4. Repeat for all 7 days. You should end up with **8 PDFs total**. 1 arrival notes + 7 Yelp days.

**The date ranges must match.** Yelp days and the arrival notes need to
start and end on the same dates — otherwise the tool is comparing different
weeks.

### D. Load it into the tool

- **Folder path:** paste the folder's path into the "Folder path" box, or
- **Upload files:** click "Upload files" and select all 8 PDFs at once.

Then click **Load** and wait for the cards to appear.
"""
