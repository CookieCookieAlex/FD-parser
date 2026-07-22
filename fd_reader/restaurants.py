"""The two restaurants this tool cross-checks reservations for: Artisans
Fine Dining and Maggie's Pub, both at the Lake Placid Lodge. Shared by
parse_reservations.py (identifying a Yelp reservation row's restaurant)
and parse_notes.py (identifying a restaurant mentioned in guest notes) --
both sides must agree on the exact restaurant name string, since
notes_cross_check.py joins them by `restaurant ==` comparison.
"""
from __future__ import annotations

RESTAURANT_KEYWORDS = {
    "artisan": "Artisans",  # covers "artisans"/"Artison" typo family too loosely on purpose
    "maggie": "Maggie's",
}
