"""Reportlab-based PDF builder for tests_synthetic/.

Places text at explicit (x0, top) coordinates matching the column bands
fd_reader.parsing.guests / fd_reader.parsing.reservations expect (see those
modules' docstrings), so a handful of drawString() calls produce a PDF the
real pdfplumber-based parsers read exactly like a real HMS/Yelp export --
without any real guest data ever touching disk.

The guest/reservation content below is designed to exercise the same
real-world note/tag patterns CLAUDE.md documents (explicit-date notes,
weekday-only notes, multi-entry Comments/Notes, room-code shorthand,
Virtuoso/breakfast-typo, outside guests, internal shorthand tokens,
room moves, and both group-booking styles) using entirely made-up guests
(see tests_synthetic/fixtures.py) and real room codes from
fd_reader/rooms/directory.py.

top is measured from the page's top edge (matches pdfplumber's `top`);
this module converts to reportlab's bottom-left-origin `y` internally.
"""
from __future__ import annotations

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter
FONT_NAME = "Helvetica"
FONT_SIZE = 9
ROW_HEIGHT = 12.0


class SyntheticPdf:
    """Accumulates pages of (text, x0, top) placements, then writes a PDF."""

    def __init__(self):
        self._pages: list[list[tuple[str, float, float]]] = [[]]

    def new_page(self) -> None:
        self._pages.append([])

    def add(self, text: str, x0: float, top: float) -> None:
        self._pages[-1].append((text, x0, top))

    def add_row(self, tokens: list[tuple[str, float]], top: float) -> None:
        """tokens: list of (text, x0) pairs sharing one printed line."""
        for text, x0 in tokens:
            self.add(text, x0, top)

    def add_wrapped_row(self, text: str, x0: float, top: float) -> None:
        """Splits text on spaces and lays tokens out left-to-right starting
        at x0, for label-value rows where exact per-word x0 doesn't matter.
        Uses a generous per-char width + gap so pdfplumber's word-grouping
        (which merges adjacent words with near-zero visual gap) never
        fuses two tokens into one -- real reportlab Helvetica-9 glyphs run
        narrower than this estimate, so the extra margin is intentional."""
        x = x0
        for token in text.split(" "):
            self.add(token, x, top)
            x += len(token) * 7.5 + 10

    def save(self, path: str) -> None:
        c = canvas.Canvas(path, pagesize=letter)
        c.setFont(FONT_NAME, FONT_SIZE)
        for page in self._pages:
            for text, x0, top in page:
                y = PAGE_HEIGHT - top - FONT_SIZE
                c.drawString(x0, y, text)
            c.showPage()
            c.setFont(FONT_NAME, FONT_SIZE)
        c.save()


# ---------------------------------------------------------------------------
# Guest-arrivals PDF: column bands from fd_reader/parsing/guests/rows.py +
# record_builder.py -- room name x0<100, guest name 100<=x0<235, status
# 235<=x0<=330, date 325<=x0<=430, guests 435<=x0<=460, rate plan
# 490<=x0<574; detail row: room type x0<100, confirmation 100<=x0<235,
# departure date 325<=x0<=430; label/value boundary at x0=160.
# ---------------------------------------------------------------------------


def _anchor_row(pdf, top, room, last, first, status, arrival, count, share, rate_plan):
    pdf.add_row(
        [
            (room, 40), (f"{last},", 110), (first, 110 + len(last) * 6 + 12),
            (status, 250), (arrival, 350),
            (str(count), 438), ("/", 447), (str(share), 454),
            (rate_plan, 500),
        ],
        top=top,
    )


def _detail_row(pdf, top, room_type, confirmation, departure):
    pdf.add_row([(room_type, 40), (confirmation, 110), (departure, 350)], top=top)


def _label_row(pdf, top, label, value):
    pdf.add((label, 40)[0], (label, 40)[1], top)
    pdf.add_wrapped_row(value, 165, top)


def build_synthetic_arrivals_pdf(path: str) -> None:
    """8 fake guests covering: a clean match, a blank room name
    (missing_room_name), a same-surname group, a 3-room exact-name group, a
    Virtuoso + breakfast-typo perk guest, a 2-record room move, a
    weekday-only note, and a multi-entry (blank-line separated)
    Comments/Notes guest."""
    pdf = SyntheticPdf()
    top = 20.0

    def advance(n=ROW_HEIGHT):
        nonlocal top
        top += n

    # Boilerplate header row -- also the exact marker text fd_reader.cli's
    # _classify_pdf() looks for to recognize this as an arrivals report.
    pdf.add_row([("Arrivals", 20), ("with", 70), ("Details", 100)], top=top)
    advance(20)

    # 1. Jackson, John -- clean match target (Yelp reservation #1).
    _anchor_row(pdf, top, "PINE", "Jackson", "John", "Reserved", "07/10/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "SPKP", "SYN-1001-1", "07/13/2026")
    advance()
    _label_row(pdf, top, "Comments / Notes:", "Artisans 7/10 @ 7PM")
    advance(20)

    # 2. Sheeran, Steve -- blank room name, room type set (missing_room_name).
    _anchor_row(pdf, top, "", "Sheeran", "Steve", "Reserved", "07/10/2026", 4, 0, "SPRING")
    advance()
    _detail_row(pdf, top, "LL1KF", "SYN-1002-1", "07/13/2026")
    advance(20)

    # 3-4. Depp, Emma / Depp, Olivia -- same-surname group (different first
    # names, same dates, different rooms).
    _anchor_row(pdf, top, "SADDLE", "Depp", "Emma", "Reserved", "07/10/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "1KF", "SYN-1003-1", "07/12/2026")
    advance(20)

    _anchor_row(pdf, top, "MOSS", "Depp", "Olivia", "Reserved", "07/10/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "1KF", "SYN-1004-1", "07/12/2026")
    advance(20)

    # 5-7. Hanks, Laura x3 -- exact-name group (3 rooms, same dates).
    for i, room in enumerate(["TAHAW", "AMPER", "MTJO"], start=5):
        _anchor_row(pdf, top, room, "Hanks", "Laura", "Reserved", "07/10/2026", 4, 0, "LEIS")
        advance()
        _detail_row(pdf, top, "1KV", f"SYN-100{i}-1", "07/13/2026")
        advance(20)

    # 8. Swift, Michael -- Virtuoso + real BREAKFAST INCLLUDED typo, in
    # Reservation Notes (matches CLAUDE.md's documented real example shape).
    _anchor_row(pdf, top, "BUCK", "Swift", "Michael", "Reserved", "07/10/2026", 2, 0, "VIRTUO")
    advance()
    _detail_row(pdf, top, "2KKF", "SYN-1008-1", "07/12/2026")
    advance()
    _label_row(
        pdf, top, "Reservation Notes:",
        "BREAKFAST INCLLUDED VIRTUOSO $100.00 VIRTUOSO CREDIT",
    )
    advance(20)

    # 9-10. Bieber, Daniel -- room move: MOSS(1KF) -> BIRCH(SBKP), departure
    # of the first record exactly equals arrival of the second.
    _anchor_row(pdf, top, "MOSS", "Bieber", "Daniel", "Reserved", "07/10/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "1KF", "SYN-1009-1", "07/12/2026")
    advance(20)

    _anchor_row(pdf, top, "BIRCH", "Bieber", "Daniel", "Reserved", "07/12/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "SBKP", "SYN-1010-1", "07/14/2026")
    advance(20)

    # 11. Clarkson, Olivia -- weekday-only note (all-caps staff style), a
    # 5-night stay so FRIDAY occurs exactly once (07/10 Fri - 07/15 Wed:
    # only 07/10 is a Friday, unambiguous).
    _anchor_row(pdf, top, "STLWTR", "Clarkson", "Olivia", "Reserved", "07/10/2026", 2, 0, "LEIS")
    advance()
    _detail_row(pdf, top, "LL1KF", "SYN-1011-1", "07/15/2026")
    advance()
    _label_row(pdf, top, "Reservation Notes:", "FRIDAY ARTISANS 7PM")
    advance(20)

    # 12. Cyrus, Sophia -- multi-entry Comments/Notes, blank-line separated
    # (two separate append_field_text calls, not one run-together string).
    _anchor_row(pdf, top, "TAMAR", "Cyrus", "Sophia", "Reserved", "07/10/2026", 2, 0, "OPSAVE")
    advance()
    _detail_row(pdf, top, "MKV", "SYN-1012-1", "07/13/2026")
    advance()
    _label_row(pdf, top, "Comments / Notes:", "Maggie's 7/11 @ 6:30PM")
    advance()
    pdf.new_page()
    top = 30.0
    pdf.add_wrapped_row("PET AMENITIES FOR RETIRED GUIDE DOG", 165, top)

    pdf.save(path)


# ---------------------------------------------------------------------------
# Yelp reservations PDF: column bands from fd_reader/parsing/reservations.py
# (time 40-95, party 100-145, guest name 170-270, notes 275-355; the
# filter-bar date line must match
# r'(?:Today|Future Day|Yesterday)\s+\w+,\s+(\w+ \d{1,2}, \d{4})').
# ---------------------------------------------------------------------------


def _write_single_day_yelp_pdf(path: str, source_date_label: str, rows: list[tuple]) -> None:
    """One reservation row (time, party, guest, notes_tags) -> one PDF, to
    match the real workflow: Yelp for Business only exports a single day
    per PDF, so a 7/8-day range means 7/8 separate files (see CLAUDE.md /
    how_to_use.md). File CONTENT (the 'Yelp for Business' marker + filter-
    bar date), not the filename, is what fd_reader.cli._classify_pdf()
    keys on -- confirmed real (a file titled 'Artisans...' can contain
    Maggie's rows) -- so these files are deliberately given generic/
    misleading names below, not name-per-restaurant, to prove that."""
    pdf = SyntheticPdf()
    pdf.add("Yelp for Business", 60, 20)
    pdf.add("Future Day " + source_date_label, 60, 360)

    top = 400.0
    for time_text, party, guest, notes in rows:
        pdf.add_row(
            [(time_text, 50), (str(party), 110), (guest, 175), (notes, 280)], top=top,
        )
        top += 20.0

    pdf.save(path)


# (filename, source_date_label, [(time, party, guest_name, notes_tags), ...])
# Filenames are deliberately generic/mixed, not restaurant-named, matching
# the real "Artisans... .pdf full of Maggie's rows" case from CLAUDE.md.
YELP_DAYS = [
    (
        "Yelp for Business.pdf", "Fri, Jul 10, 2026",
        [("7:00", 2, "John Jackson", "artisans PINE")],
    ),
    (
        "Yelp for Business2.pdf", "Fri, Jul 10, 2026",
        # Emma Depp -- room-code hint disagrees with her real room (SADDLE)
        # -- a genuine staff note-entry mismatch, must flag not silently trust.
        [("6:00", 2, "Emma Depp", "artisans, STLWTR")],
    ),
    (
        "Artisans at the Lake Placid Lodge _ Yelp for Business.pdf", "Sat, Jul 11, 2026",
        # HANKS -- surname only, hint says "3 rooms" (no specific room) --
        # ties across the 3-room exact-name group via linked_group.
        [("6:30", 4, "HANKS", "artisans 3 rooms")],
    ),
    (
        "Artisans at the Lake Placid Lodge _ Yelp for Business2.pdf", "Fri, Jul 10, 2026",
        [("7:30", 2, "Michael Swift", "artisans BUCK")],
    ),
    (
        "Yelp for Business3.pdf", "Sun, Jul 12, 2026",
        # Daniel Bieber -- matches the LATER leg of his room move (BIRCH).
        # Filename says nothing about restaurant -- content decides (Maggie's).
        [("6:00", 2, "Daniel Bieber", "maggie's BIRCH")],
    ),
    (
        "Artisans at the Lake Placid Lodge _ Yelp for Business3.pdf", "Fri, Jul 10, 2026",
        # Olivia Clarkson -- matches her weekday-only Friday note.
        [("7:00", 2, "Olivia Clarkson", "artisans STLWTR")],
    ),
    (
        "Yelp for Business4.pdf", "Fri, Jul 10, 2026",
        # Outside guest -- no in-house room hint at all.
        [("8:00", 2, "bill jennings", "artisans off property no allergies")],
    ),
    (
        "Artisans at the Lake Placid Lodge _ Yelp for Business4.pdf", "Sat, Jul 11, 2026",
        # Punctuated room-code hint + internal shorthand token (GH) -- per
        # CLAUDE.md's real "Artisans- St.regis" (-> STREG) / "...GH" examples.
        [("6:45", 2, "Sophia Cyrus", "Artisans- St.regis GH")],
    ),
]


def build_synthetic_yelp_pdf(path: str, source_date_label: str = "Fri, Jul 10, 2026") -> None:
    """Single-file convenience wrapper (used by tests that only need one
    day) -- writes just YELP_DAYS[0]'s content under the given path/date."""
    _, _, rows = YELP_DAYS[0]
    _write_single_day_yelp_pdf(path, source_date_label, rows)


def build_synthetic_yelp_pdfs(folder: str) -> list[str]:
    """Writes all 8 single-day Yelp PDFs (see YELP_DAYS) into `folder`,
    using their documented (deliberately generic/mixed) filenames. Returns
    the list of paths written, in YELP_DAYS order."""
    import os

    paths = []
    for filename, source_date_label, rows in YELP_DAYS:
        path = os.path.join(folder, filename)
        _write_single_day_yelp_pdf(path, source_date_label, rows)
        paths.append(path)
    return paths
