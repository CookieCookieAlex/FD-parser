"""Builds a visually-annotated replica of the guest-arrivals ("Arrivals
with Details") PDF, with the column x0-bands fd_reader.parsing.guests
actually reads drawn as colored guide boxes + captions -- same approach as
tests_synthetic/annotated_replica.py, but for the guest-list side instead
of Yelp.

Deliberately DOES NOT include VIP Level / Address / Preferences / Last
Stay Property / Lifetime Revenue / Booking Agency / IATA -- those are
real optional fields the parser supports, but per user direction this
replica only needs Guest Notes / Reservation Notes / Comments-Notes plus
the core anchor/detail-row fields, to keep the fixture focused on what's
actually being tested here.

Guest names are all made up (first name + celebrity surname, matching the
convention used elsewhere in tests_synthetic/). Confirmation numbers are
randomly generated (shaped like the real <10-digit>-<1-digit> format) --
never real guest IDs. Real room codes and rate plans are used
(fd_reader/rooms/directory.py) where it matters; other values are
placeholders.

13 guests total, covering: a clean baseline match, a blank room name with
room type still set (the "missing_room_name" flag case from CLAUDE.md),
all 3 note fields (Guest Notes / Reservation Notes / Comments-Notes)
including the real Virtuoso + "BREAKFAST INCLLUDED" typo and the ALL-CAPS
weekday-only note style, a note mentioning a reservation the Yelp side
won't have, an unusual (non-"Reserved") status, a 2-record room move, a
2-room exact-name group booking, a weekday note that's genuinely
ambiguous over a long stay (both Fridays fall inside the window), and two
sofa-bed-request cases (match/sofa_bed_check.py): one in a room that has
one (satisfied, orange badge) and one in a room that doesn't (unsatisfied,
red alert -- likely needs a room move).

IMPORTANT layout constraint discovered while building this: the real
parser (fd_reader/parsing/guests/__init__.py) treats whatever row comes
IMMEDIATELY after a record-anchor row as the detail row, unconditionally
(see `expect_detail_row`). So a caption CANNOT be its own row between the
anchor row and the detail row -- the parser would consume the caption
text as if it were the detail row and silently misparse it. The fix used
below: draw one small caption block ABOVE each entire guest block (not
between individual rows within it), so every row the parser actually
walks is real content, and the captions live in a completely separate
part of the page that the row-classifier never reaches (it's positioned
below the LABEL_VALUE_BOUNDARY-blind text-search zone, and its own text
doesn't match any label or anchor pattern).

Not a test fixture -- this is a one-off diagram generator, run manually:
    .venv/bin/python -m tests_synthetic.guest_notes_replica
"""
from __future__ import annotations

import random

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter

# Fake confirmation numbers, shaped like the real <10-digit>-<1-digit>
# format (e.g. CLAUDE.md's real "9155988611-1") but randomly generated --
# seeded so the same numbers are reused across annotated/clean rebuilds.
_CONF_RNG = random.Random(2026)


def _fake_confirmation_number() -> str:
    return f"{_CONF_RNG.randint(1_000_000_000, 9_999_999_999)}-1"


# Same bands as fd_reader/parsing/guests/rows.py + record_builder.py.
COL_ROOM = (0, 100)            # anchor row: room name / detail row: room type
COL_NAME_OR_CONF = (100, 235)  # anchor row: guest name / detail row: confirmation #
COL_STATUS = (235, 330)
COL_DATE = (325, 430)          # anchor row: arrival / detail row: departure
COL_GUESTS = (435, 460)
COL_RATE_PLAN = (490, 574)
LABEL_VALUE_BOUNDARY = 160

_BAND_COLOR = HexColor("#3B82F6")
_BAND_FILL = HexColor("#DBEAFE")
_LABEL_COLOR = HexColor("#1D4ED8")
_ERROR_COLOR = HexColor("#DC2626")
_ERROR_FILL = HexColor("#FEE2E2")

ROW_HEIGHT = 12


def _top_to_y(top: float, font_size: float = 9) -> float:
    return PAGE_HEIGHT - top - font_size


def _draw_rect(c, x0, x1, top_start, top_end, fill, border):
    y_top = _top_to_y(top_start, 0)
    y_bottom = _top_to_y(top_end, 0)
    c.setFillColor(fill)
    c.setStrokeColor(border)
    c.rect(x0, y_bottom, x1 - x0, y_top - y_bottom, fill=1, stroke=1)


def _draw_caption_line(c, top, x0, label, text_color):
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 6)
    c.drawString(x0 + 1, _top_to_y(top, 0) - 5, label)


def draw_field_caption_legend(c, top, room_error=False) -> float:
    """One small caption strip covering ALL the anchor/detail-row column
    bands at once, drawn ABOVE a guest block rather than between its
    rows (see module docstring for why). Returns the next free `top`."""
    box_bottom = top + ROW_HEIGHT - 2
    box_top = top - 2

    room_fill, room_border = (_ERROR_FILL, _ERROR_COLOR) if room_error else (_BAND_FILL, _BAND_COLOR)
    _draw_rect(c, *COL_ROOM, box_top, box_bottom, room_fill, room_border)
    _draw_rect(c, *COL_NAME_OR_CONF, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_rect(c, *COL_STATUS, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_rect(c, *COL_DATE, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_rect(c, *COL_GUESTS, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_rect(c, *COL_RATE_PLAN, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)

    _draw_caption_line(c, top, COL_ROOM[0], "ERROR: room BLANK" if room_error else "room_name/room_type", _ERROR_COLOR if room_error else _LABEL_COLOR)
    _draw_caption_line(c, top, COL_NAME_OR_CONF[0], "guest_name/confirmation_#", _LABEL_COLOR)
    _draw_caption_line(c, top, COL_STATUS[0], "status", _LABEL_COLOR)
    _draw_caption_line(c, top, COL_DATE[0], "arrival/departure_date", _LABEL_COLOR)
    _draw_caption_line(c, top, COL_GUESTS[0], "guests", _LABEL_COLOR)
    _draw_caption_line(c, top, COL_RATE_PLAN[0], "rate_plan", _LABEL_COLOR)

    return top + ROW_HEIGHT + 4


def draw_note_field_caption(c, top, field_name: str) -> float:
    box_bottom = top + ROW_HEIGHT - 2
    box_top = top - 2
    _draw_rect(c, 0, LABEL_VALUE_BOUNDARY, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_rect(c, LABEL_VALUE_BOUNDARY, 574, box_top, box_bottom, _BAND_FILL, _BAND_COLOR)
    _draw_caption_line(c, top, 0, "label (text match)", _LABEL_COLOR)
    _draw_caption_line(c, top, LABEL_VALUE_BOUNDARY, f"PARSED: {field_name}", _LABEL_COLOR)
    return top + ROW_HEIGHT + 4


def draw_anchor_row(c, top, room, last, first, status, arrival, count, share, rate_plan) -> float:
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    if room:
        c.drawString(10, _top_to_y(top), room)
    c.drawString(110, _top_to_y(top), f"{last}, {first}")
    c.drawString(250, _top_to_y(top), status)
    c.drawString(350, _top_to_y(top), arrival)
    c.drawString(438, _top_to_y(top), str(count))
    c.drawString(447, _top_to_y(top), "/")
    c.drawString(454, _top_to_y(top), str(share))
    c.drawString(500, _top_to_y(top), rate_plan)
    return top + ROW_HEIGHT + 2


def draw_detail_row(c, top, room_type, confirmation, departure) -> float:
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(10, _top_to_y(top), room_type)
    c.drawString(110, _top_to_y(top), confirmation)
    c.drawString(350, _top_to_y(top), departure)
    return top + ROW_HEIGHT + 2


def draw_label_row(c, top, label, value) -> float:
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(10, _top_to_y(top), label)

    x = 165
    line_top = top
    words = value.split(" ")
    line_words: list[str] = []
    for w in words:
        line_words.append(w)
        x += len(w) * 6 + 6
        if x > 550:
            c.drawString(165, _top_to_y(line_top), " ".join(line_words))
            line_words = []
            x = 165
            line_top += ROW_HEIGHT
    if line_words:
        c.drawString(165, _top_to_y(line_top), " ".join(line_words))

    return line_top + ROW_HEIGHT + 2


def _build(path: str, annotated: bool) -> None:
    c = canvas.Canvas(path, pagesize=letter)
    top = 20.0
    _CONF_RNG.seed(2026)  # reset so annotated/clean builds get identical fake IDs
    conf_1 = _fake_confirmation_number()
    conf_2 = _fake_confirmation_number()
    conf_3 = _fake_confirmation_number()
    conf_4 = _fake_confirmation_number()
    conf_5 = _fake_confirmation_number()
    conf_6a = _fake_confirmation_number()
    conf_6b = _fake_confirmation_number()
    conf_7a = _fake_confirmation_number()
    conf_7b = _fake_confirmation_number()
    conf_8 = _fake_confirmation_number()
    conf_9 = _fake_confirmation_number()
    conf_10 = _fake_confirmation_number()
    conf_11 = _fake_confirmation_number()
    conf_12 = _fake_confirmation_number()
    conf_13 = _fake_confirmation_number()

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(HexColor("#111827"))
    c.drawString(20, _top_to_y(top), "Arrivals with Details")
    top += 26

    def block(room, last, first, arrival, count, share, rate_plan, room_type, conf, departure,
              notes: list[tuple[str, str, str]], room_error=False):
        """notes: list of (label, value, field_name)."""
        nonlocal top
        if annotated:
            top = draw_field_caption_legend(c, top, room_error=room_error)
        top = draw_anchor_row(c, top, room, last, first, "Reserved", arrival, count, share, rate_plan)
        top = draw_detail_row(c, top, room_type, conf, departure)
        for label, value, field_name in notes:
            if annotated:
                top = draw_note_field_caption(c, top, field_name)
            top = draw_label_row(c, top, label, value)
        top += 14

    # 1. Jackson, John -- clean baseline, Comments/Notes mentions a
    # restaurant reservation the Yelp side should confirm/deny.
    block(
        "PINE", "Jackson", "John", "07/10/2026", 2, 0, "LEIS", "SPKP", conf_1, "07/13/2026",
        [("Comments / Notes:", "Artisans 7/10 @ 7PM", "comments_notes")],
    )

    # 2. Sheeran, Steve -- blank room name, room type set. This is the
    # deliberate error case: parser must flag missing_room_name.
    block(
        "", "Sheeran", "Steve", "07/11/2026", 4, 0, "SPRING", "LL1KF", conf_2, "07/14/2026",
        [], room_error=True,
    )

    # 3. Depp, Emma -- Guest Notes with intentional messy spacing (real-
    # world typo-like data), Reservation Notes with Virtuoso + the real
    # "INCLLUDED" typo, Comments/Notes with the ALL-CAPS weekday style.
    block(
        "SADDLE", "Depp", "Emma", "07/10/2026", 2, 0, "VIRTUO", "1KF", conf_3, "07/15/2026",
        [
            ("Guest Notes:", "no allergies noted , pet friendly rm requstd", "guest_notes"),
            ("Reservation Notes:", "BREAKFAST INCLLUDED VIRTUOSO $100.00 VIRTUOSO CREDIT", "reservation_notes"),
            ("Comments / Notes:", "TUESDAY MAGGIES 6PM, WEDNESDAY ARTISANS 6PM", "comments_notes"),
        ],
    )

    # 4. Hanks, Laura -- Comments/Notes references a restaurant/date the
    # Yelp side won't actually have (a "note says there's a reservation
    # but none was found" case) -- a deliberate mismatch to test against,
    # not a parser bug.
    block(
        "MOSS", "Hanks", "Laura", "07/12/2026", 2, 0, "LEIS", "1KF", conf_4, "07/16/2026",
        [("Comments / Notes:", "FRIDAY ARTISANS 8PM SOLO TRAVELER", "comments_notes")],
    )

    # 5. Swift, Michael -- unusual (non-"Reserved") status, should still
    # parse but pick up an unknown_status warning rather than crash.
    if annotated:
        top = draw_field_caption_legend(c, top)
    top = draw_anchor_row(c, top, "BUCK", "Swift", "Michael", "CheckedIn", "07/10/2026", 2, 0, "COMP")
    top = draw_detail_row(c, top, "2KKF", conf_5, "07/12/2026")
    top += 14

    # 6a/6b. Bieber, Daniel -- room move: MOSS(1KF) -> BIRCH(SBKP), the
    # first record's departure exactly equals the second's arrival.
    block(
        "MOSS", "Bieber", "Daniel", "07/13/2026", 2, 0, "LEIS", "1KF", conf_6a, "07/15/2026",
        [("Reservation Notes:", "Room moved at guest's request, see notes.", "reservation_notes")],
    )
    block(
        "BIRCH", "Bieber", "Daniel", "07/15/2026", 2, 0, "LEIS", "SBKP", conf_6b, "07/17/2026",
        [],
    )

    # 7a/7b. Clarkson, Olivia -- exact-name group booking, 2 rooms, same
    # dates -- must not be treated as a duplicate/error.
    block(
        "TAMAR", "Clarkson", "Olivia", "07/11/2026", 3, 0, "OPSAVE", "MKV", conf_7a, "07/14/2026",
        [("Comments / Notes:", "7/12 & 7/13-artisans @ 7pm 2ppl", "comments_notes")],
    )
    block(
        "STREG", "Clarkson", "Olivia", "07/11/2026", 3, 0, "OPSAVE", "MKV", conf_7b, "07/14/2026",
        [],
    )

    # 8. Cyrus, Sophia -- a 12-night stay where an ALL-CAPS weekday-only
    # note is genuinely ambiguous (both Fridays fall inside the window) --
    # must be flagged, not guessed at.
    block(
        "PLACID", "Cyrus", "Sophia", "07/06/2026", 2, 0, "LTS1", "LU1KF", conf_8, "07/18/2026",
        [("Reservation Notes:", "FRIDAY ARTISANS 7PM, SATURDAY MAGGIES 7PM", "reservation_notes")],
    )

    # 9. Hopkins, Grace -- the mismatch case: this note names a specific
    # restaurant + date. If a Yelp reservation for Grace Hopkins on 7/12
    # is ever paired with this guest list and shows a DIFFERENT restaurant
    # (e.g. Maggie's instead of Artisans), notes_cross_check.py's
    # cross_check_notes() must surface that as a "mismatch" (likely a
    # staff note-entry error), not silently drop it.
    block(
        "AUSABL", "Hopkins", "Grace", "07/11/2026", 2, 0, "LEIS", "LU1KF", conf_9, "07/13/2026",
        [("Comments / Notes:", "Artisans 7/12 @ 6:30PM", "comments_notes")],
    )

    # 10. Depp, Olivia -- unrelated same-surname guest to #3 (Depp, Emma),
    # different room/stay, in-house the same night (7/10). Paired with a
    # bare "DEPP" Yelp row (no room hint) in yelp_day_a.pdf, this can't be
    # told apart by name alone -- match_reservations() must attach it to
    # one of the two Depps (flagged "ambiguous_name_match", RED, naming
    # the other one) rather than silently dropping the reservation.
    block(
        "BUCK", "Depp", "Olivia", "07/09/2026", 2, 0, "LEIS", "2KKF", conf_10, "07/15/2026",
        [],
    )

    # 11. Smith, John -- Comments/Notes says Artisans 7/11 @ 7PM, but the
    # actual Yelp reservation paired against this (yelp_day_b.pdf, Sat Jul
    # 11) is at a different time. cross_check_notes() must flag this
    # "time_mismatch" (RED) rather than calling it "matched" just because
    # the restaurant and date agree.
    block(
        "TAHAW", "Smith", "John", "07/11/2026", 2, 0, "LEIS", "1KV", conf_11, "07/14/2026",
        [("Comments / Notes:", "Artisans 7/11 @ 7PM", "comments_notes")],
    )

    # 12. Turner, Grace -- sofa-bed request in a room that HAS one (RAQTTE
    # is Lakeside, has_sofa_bed=True per rooms/directory.py) --
    # match/sofa_bed_check.py's "satisfied" case, shown as an orange
    # informational badge, not an alert.
    block(
        "RAQTTE", "Turner", "Grace", "07/10/2026", 2, 0, "LEIS", "L1KF", conf_12, "07/12/2026",
        [("Comments / Notes:", "Requesting a sofa bed for the room.", "comments_notes")],
    )

    # 13. Wilson, Henry -- sofa-bed request in a room that does NOT have
    # one (WTFACE is Main Lodge, has_sofa_bed=False) --
    # match/sofa_bed_check.py's "unsatisfied" case, a real staff action
    # item (likely needs a room move), shown as a red alert banner.
    block(
        "WTFACE", "Wilson", "Henry", "07/10/2026", 2, 0, "LEIS", "MWKV", conf_13, "07/12/2026",
        [("Guest Notes:", "Guest asked for a sofa bed if available.", "guest_notes")],
    )

    c.showPage()
    c.save()


def build_annotated_guest_notes_replica(path: str) -> None:
    _build(path, annotated=True)


def build_clean_guest_notes_replica(path: str) -> None:
    _build(path, annotated=False)


if __name__ == "__main__":
    build_annotated_guest_notes_replica("tests_synthetic/sample_output/annotated_guest_notes_replica.pdf")
    print("wrote tests_synthetic/sample_output/annotated_guest_notes_replica.pdf")
    build_clean_guest_notes_replica("tests_synthetic/sample_output/clean_guest_notes_replica.pdf")
    print("wrote tests_synthetic/sample_output/clean_guest_notes_replica.pdf")
