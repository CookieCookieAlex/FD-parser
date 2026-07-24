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


def find_restaurant(text: str) -> str | None:
    """First RESTAURANT_KEYWORDS match in `text` (case-insensitive), or
    None. Shared by parsing/notes and parsing/reservations/fields.py so
    both sides of the match resolve a restaurant name the same way."""
    lowered = text.lower()
    for keyword, name in RESTAURANT_KEYWORDS.items():
        if keyword in lowered:
            return name
    return None
