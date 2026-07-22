"""Builds 6 clean (no annotation boxes) Yelp for Business reservation-day
replicas, each with a different reservation count (4-14), for testing
against a range of file sizes -- not just the single-day, single-
reservation fixtures used elsewhere in tests_synthetic/.

Guest names are all made up (see tests_synthetic/fixtures.py-style
first-name + celebrity-surname pattern); phone numbers are randomized
518-area-code numbers (Lake Placid, NY's real area code, but the rest of
each number is random and fake).

Not a pytest fixture -- this is a one-off generator, run manually:
    .venv/bin/python -m tests_synthetic.yelp_replica_batch
"""
from __future__ import annotations

import random

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter

# Same bands as fd_reader/parsing/reservations.py.
COL_TIME = (40, 95)
COL_PARTY = (100, 145)
COL_GUEST = (170, 270)
COL_NOTES = (275, 355)

_FIRST_NAMES = [
    "John", "Emma", "Steve", "Laura", "Michael", "Olivia", "Daniel", "Sophia",
    "Grace", "Ryan", "Amy", "Ben", "Claire", "Tom", "Nina", "Owen", "Kate",
    "Leo", "Zoe", "Max",
]
_LAST_NAMES = [
    "Jackson", "Sheeran", "Depp", "Hanks", "Swift", "Clarkson", "Bieber",
    "Cyrus", "Hopkins", "Winslet", "Pitt", "Portman", "Damon", "Blunt",
    "Cooper", "Adams", "Reynolds", "Lively", "Gosling", "Stone",
]
_ROOM_CODES = [
    "PINE", "BIRCH", "BUCK", "HAWK", "KIWA", "MARBLE", "LOOK", "AMPER",
    "TAHAW", "MCKEN", "STARM", "MOSS", "ROND", "SADDLE", "MTMARCY", "MTJO",
    "OWLS", "PLACID", "AUSABL", "RAQTTE", "CASCDE", "STLWTR", "LOON",
    "TAMAR", "STREG", "HEARTH", "TREE", "WTFACE",
]
_RESTAURANT_HINTS = ["artisans", "maggie's"]
_OUTSIDE_GUEST_NOTES = [
    "artisans off property no allergies",
    "maggie's off property",
]
_TIMES = ["6:00", "6:30", "7:00", "7:30", "8:00", "5:30", "8:30"]

_BAND_COLOR = HexColor("#3B82F6")


def _top_to_y(top: float, font_size: float = 9) -> float:
    return PAGE_HEIGHT - top - font_size


def _random_phone(rng: random.Random) -> str:
    """518 is Lake Placid, NY's real area code; the rest of the number is
    randomly generated and not a real phone number."""
    exchange = rng.randint(200, 999)
    line = rng.randint(0, 9999)
    return f"(518) {exchange}-{line:04d}"


def _draw_row(c, top, time_text, party, guest, notes_lines, phone=None):
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(COL_TIME[0], _top_to_y(top), time_text)
    c.drawString(COL_PARTY[0], _top_to_y(top), str(party))
    c.drawString(COL_GUEST[0], _top_to_y(top), guest)
    line_top = top
    for line in notes_lines:
        c.drawString(COL_NOTES[0], _top_to_y(line_top), line)
        line_top += 12
    if phone:
        c.setFont("Helvetica", 8)
        c.setFillColor(HexColor("#6B7280"))
        c.drawString(COL_GUEST[0], _top_to_y(top + 12), phone)
    return line_top + (12 if not notes_lines else 0)


def _generate_reservations(rng: random.Random, count: int, exclude_surnames: set[str] | None = None) -> list[dict]:
    """exclude_surnames: last names to never generate -- used to guarantee
    no accidental collision with tests_synthetic/guest_notes_replica.py's
    fixed guest roster on files meant to pair with it (e.g. yelp_day_c.pdf
    carries a deliberate, unambiguous Grace Hopkins/Maggie's mismatch row;
    a randomly-generated second "Hopkins" reservation on the same day
    would create real matching ambiguity, not a bug -- exclude the surname
    outright instead of fighting the fuzzy matcher)."""
    exclude_surnames = exclude_surnames or set()
    available_last_names = [n for n in _LAST_NAMES if n not in exclude_surnames]

    reservations = []
    used_names = set()
    for i in range(count):
        while True:
            name = f"{rng.choice(_FIRST_NAMES)} {rng.choice(available_last_names)}"
            if name not in used_names:
                used_names.add(name)
                break

        # Every 5th reservation is an outside guest (no in-house hint).
        if i % 5 == 4:
            notes = [rng.choice(_OUTSIDE_GUEST_NOTES)]
            has_phone = False
        else:
            restaurant = rng.choice(_RESTAURANT_HINTS)
            room = rng.choice(_ROOM_CODES)
            notes = [f"{restaurant} {room}"]
            # Occasionally wrap onto a second Notes & Tags line.
            if rng.random() < 0.25:
                notes.append(rng.choice(["VVIP", "allergy note", "anniversary", "GH"]))
            has_phone = rng.random() < 0.4

        reservations.append(
            dict(
                time=rng.choice(_TIMES),
                party=rng.randint(1, 6),
                guest=name,
                notes=notes,
                phone=_random_phone(rng) if has_phone else None,
            )
        )
    return reservations


def build_yelp_replica(
    path: str, seed: int, reservation_count: int, date_label: str,
    extra_reservations: list[dict] | None = None, exclude_surnames: set[str] | None = None,
) -> None:
    rng = random.Random(seed)
    reservations = _generate_reservations(rng, reservation_count, exclude_surnames=exclude_surnames)
    if extra_reservations:
        reservations = reservations + extra_reservations

    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#111827"))
    c.drawString(30, PAGE_HEIGHT - 12, "Yelp for Business Reservations")
    c.drawString(30, PAGE_HEIGHT - 24, "7/10/26, 12:17 PM  Artisans at the Lake Placid Lodge | Yelp for Business")

    actual_count = len(reservations)
    top = 45
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(
        40, _top_to_y(top),
        f"Total Covers: {sum(r['party'] for r in reservations)}   "
        f"Total Reservations: {actual_count}   Confirmed: 1   Booked: {actual_count - 1}   "
        f"Online: 0   In House: {actual_count}",
    )

    date_top = 84
    c.drawString(60, _top_to_y(date_top), f"Future Day {date_label}")

    header_top = 100
    c.setFont("Helvetica-Bold", 8)
    c.drawString(COL_TIME[0], _top_to_y(header_top), "Time")
    c.drawString(COL_PARTY[0], _top_to_y(header_top), "Party")
    c.drawString(COL_GUEST[0], _top_to_y(header_top), "Guest Details")
    c.drawString(COL_NOTES[0], _top_to_y(header_top), "Notes & Tags")

    top = 130
    for r in reservations:
        top = _draw_row(c, top, r["time"], r["party"], r["guest"], r["notes"], phone=r["phone"])
        top += 12  # gap between reservations
        if top > 670:
            c.showPage()
            c.setFont("Helvetica", 9)
            top = 40

    # Footer -- always its own row, at least 15pt below the last reservation.
    footer_top = max(top + 15, 700)
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#6B7280"))
    footer_text = (
        "About  Discover  Languages  Get the Yelp for Business app  "
        "Content Guidelines  Copyright (C) Yelp Inc.  biz.yelp.com"
    )
    c.drawString(40, _top_to_y(footer_top), footer_text)

    c.showPage()
    c.save()


# (filename, seed, reservation_count, date_label)
BATCH = [
    ("yelp_day_a.pdf", 101, 4, "Fri, Jul 10, 2026"),
    ("yelp_day_b.pdf", 102, 6, "Sat, Jul 11, 2026"),
    ("yelp_day_c.pdf", 103, 8, "Sun, Jul 12, 2026"),
    ("yelp_day_d.pdf", 104, 10, "Mon, Jul 13, 2026"),
    ("yelp_day_e.pdf", 105, 12, "Tue, Jul 14, 2026"),
    ("yelp_day_f.pdf", 106, 14, "Wed, Jul 15, 2026"),
]

# yelp_day_a.pdf (Fri, Jul 10, 2026) gets one fixed extra row: a bare
# "DEPP" reservation, no room hint. tests_synthetic/guest_notes_replica.py
# has TWO unrelated same-surname guests in-house that night -- guest #3
# (Depp, Emma, 07/10-07/15) and guest #10 (Depp, Olivia, 07/09-07/15) --
# so pairing clean_guest_notes_replica.pdf with yelp_day_a.pdf makes
# match_reservations() unable to tell them apart by name alone. It must
# attach the reservation to one of them (flagged "ambiguous_name_match",
# RED, naming the other Depp as a possible match) rather than silently
# dropping it because neither is a clean, certain match.
_YELP_DAY_A_EXTRA = [
    dict(time="7:00", party=2, guest="DEPP", notes=["artisans"], phone=None),
]

# yelp_day_b.pdf (Sat, Jul 11, 2026) gets one fixed extra row: John Smith
# at 6:30 -- but tests_synthetic/guest_notes_replica.py's guest #11
# (Smith, John) has a Comments/Notes entry reading "Artisans 7/11 @ 7PM",
# a different time. Restaurant and date agree, only the time disagrees --
# cross_check_notes() must flag this "time_mismatch" (RED) rather than
# calling it a clean "matched" just because restaurant+date line up.
_YELP_DAY_B_EXTRA = [
    dict(time="6:30", party=2, guest="John Smith", notes=["artisans TAHAW"], phone=None),
]

# yelp_day_c.pdf (Sun, Jul 12, 2026) gets one fixed extra row: Grace
# Hopkins at Maggie's. This is the deliberate mismatch test case --
# tests_synthetic/guest_notes_replica.py's guest #9 (Hopkins, Grace) has
# a Comments/Notes entry reading "Artisans 7/12 @ 6:30PM", so pairing
# clean_guest_notes_replica.pdf with yelp_day_c.pdf makes
# cross_check_notes() surface a real "mismatch" (note says Artisans, Yelp
# actually shows Maggie's on the same date) -- verified in the terminal
# before this row was added to an actual file.
_YELP_DAY_C_EXTRA = [
    dict(time="6:30", party=2, guest="Grace Hopkins", notes=["maggie's AUSABL"], phone=None),
]

# yelp_day_d.pdf (Mon, Jul 13, 2026) gets one fixed extra row: a bare
# surname reservation, "HANKS" -- no first name, no room hint in Notes &
# Tags. tests_synthetic/guest_notes_replica.py's guest #4 (Hanks, Laura)
# is in-house 07/12-07/16/2026, which covers this date, so pairing
# clean_guest_notes_replica.pdf with yelp_day_d.pdf makes
# match_reservations() resolve this via the surname-only fallback and
# flag it "surname_only_no_room_hint" -- rendered RED / "Potential
# outside guest" per fd_reader/report/blocks.py, since a bare last name
# with no room hint isn't strong enough to be fully confident it's really
# her and not an unrelated person who happens to share her surname.
_YELP_DAY_D_EXTRA = [
    dict(time="7:00", party=2, guest="HANKS", notes=["artisans"], phone=None),
]


def build_batch(folder: str) -> list[str]:
    import os

    extras = {
        "yelp_day_a.pdf": _YELP_DAY_A_EXTRA,
        "yelp_day_b.pdf": _YELP_DAY_B_EXTRA,
        "yelp_day_c.pdf": _YELP_DAY_C_EXTRA,
        "yelp_day_d.pdf": _YELP_DAY_D_EXTRA,
    }
    excludes = {
        "yelp_day_a.pdf": {"Depp"},
        "yelp_day_c.pdf": {"Hopkins"},
        "yelp_day_d.pdf": {"Hanks"},
    }

    paths = []
    for filename, seed, count, date_label in BATCH:
        path = os.path.join(folder, filename)
        extra = extras.get(filename)
        exclude = excludes.get(filename)
        build_yelp_replica(
            path, seed=seed, reservation_count=count, date_label=date_label,
            extra_reservations=extra, exclude_surnames=exclude,
        )
        paths.append(path)
    return paths


if __name__ == "__main__":
    paths = build_batch("tests_synthetic/sample_output")
    for p in paths:
        print("wrote", p)
