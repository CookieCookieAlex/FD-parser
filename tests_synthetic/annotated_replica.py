"""Builds a visually-annotated replica of a Yelp for Business reservations
PDF export -- same page shape/columns a real biz.yelp.com print produces,
but with the column x0-bands fd_reader.parsing.reservations actually reads
(see that module's COL_TIME/COL_PARTY/COL_GUEST/COL_NOTES + its docstring)
drawn as colored guide boxes with labels, so it's visible on the page
which pixels the parser is looking at for each field.

Not a test fixture -- this is a one-off diagram generator, run manually:
    .venv/bin/python -m tests_synthetic.annotated_replica
"""
from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter

# Same bands as fd_reader/parsing/reservations.py.
COL_TIME = (40, 95)
COL_PARTY = (100, 145)
COL_GUEST = (170, 270)
COL_NOTES = (275, 355)

_BAND_COLOR = HexColor("#3B82F6")
_BAND_FILL = HexColor("#DBEAFE")
_LABEL_COLOR = HexColor("#1D4ED8")
_IGNORED_COLOR = HexColor("#9CA3AF")
_IGNORED_FILL = HexColor("#F3F4F6")


def _top_to_y(top: float, font_size: float = 9) -> float:
    return PAGE_HEIGHT - top - font_size


def _draw_band(c, x0: float, x1: float, top_start: float, top_end: float, label: str, fill, border, text_color):
    y_top = _top_to_y(top_start, 0)
    y_bottom = _top_to_y(top_end, 0)
    c.setFillColor(fill)
    c.setStrokeColor(border)
    c.rect(x0, y_bottom, x1 - x0, y_top - y_bottom, fill=1, stroke=1)
    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 6)
    c.drawString(x0 + 2, y_top - 8, label)


def _draw_ignored_band(c, x0: float, x1: float, top_start: float, top_end: float, label: str):
    _draw_band(c, x0, x1, top_start, top_end, label, _IGNORED_FILL, _IGNORED_COLOR, _IGNORED_COLOR)


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


def _draw_shared_content(c, annotated: bool) -> None:
    """Draws the same replica page content either way; `annotated` toggles
    the colored column-band boxes/labels on top of it."""
    # ---- Boilerplate: browser nav / page title (ignored by the parser) ---
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#111827"))
    c.drawString(30, PAGE_HEIGHT - 12, "Yelp for Business Reservations")
    c.drawString(30, PAGE_HEIGHT - 24, "7/10/26, 12:17 PM  Artisans at the Lake Placid Lodge | Yelp for Business")
    if annotated:
        _draw_ignored_band(c, 20, 560, 5, 30, "IGNORED: page title / browser chrome (top < 60)")

    # ---- Summary header (ignored) -----------------------------------------
    top = 45
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(40, _top_to_y(top), "Total Covers: 8   Total Reservations: 4   Confirmed: 1   Booked: 3   Online: 0   In House: 4")
    if annotated:
        _draw_ignored_band(c, 20, 560, top - 3, top + 12, "IGNORED: summary counts (never parsed)")

    # ---- Filter bar (parsed: source_date) ----------------------------------
    # Real date text is drawn on its own `top`, never sharing a row with the
    # annotation label -- pdfplumber groups same-line words by `top`, so
    # overlapping the two would fuse them into one garbled row (confirmed
    # while building this the first time).
    label_top, date_top = 72, 84
    if annotated:
        _draw_band(c, 55, 300, label_top - 3, date_top + 12, "PARSED: source_date (filter bar regex)", _BAND_FILL, _BAND_COLOR, _LABEL_COLOR)
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#111827"))
    c.drawString(60, _top_to_y(date_top), "Future Day Fri, Jul 10, 2026")

    # ---- Column header row (ignored by text match) -------------------------
    top = 100
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(HexColor("#111827"))
    c.drawString(40, _top_to_y(top), "Time")
    c.drawString(100, _top_to_y(top), "Party")
    c.drawString(170, _top_to_y(top), "Guest Details")
    c.drawString(275, _top_to_y(top), "Notes & Tags")
    if annotated:
        _draw_ignored_band(c, 20, 560, top - 3, top + 12, 'IGNORED: header row (text startswith "Time Party" / "Guest Details")')

        # The real column bands (COL_TIME/COL_PARTY/COL_GUEST/COL_NOTES) are
        # pure x0 ranges with no vertical limit of their own -- they apply
        # to every row on the page. What actually bounds the reservation
        # area is row.top < 60 (page-title zone, always ignored) at the top
        # and _footer_start_top() (first row matching a footer phrase) at
        # the bottom, wherever that lands. Boxes extend down to just above
        # this replica's footer (top=700) to reflect that real range.
        legend_top, legend_bottom = 118, 695
        _draw_band(c, *COL_TIME, legend_top, legend_bottom, f"COL_TIME {COL_TIME}", _BAND_FILL, _BAND_COLOR, _LABEL_COLOR)
        _draw_band(c, *COL_PARTY, legend_top, legend_bottom, f"COL_PARTY {COL_PARTY}", _BAND_FILL, _BAND_COLOR, _LABEL_COLOR)
        _draw_band(c, *COL_GUEST, legend_top, legend_bottom, f"COL_GUEST {COL_GUEST}", _BAND_FILL, _BAND_COLOR, _LABEL_COLOR)
        _draw_band(c, *COL_NOTES, legend_top, legend_bottom, f"COL_NOTES {COL_NOTES}", _BAND_FILL, _BAND_COLOR, _LABEL_COLOR)

    # 1. Clean reservation, single-line notes.
    _draw_row(c, 130, "7:00", 2, "John Jackson", ["artisans PINE"])

    # 2. Reservation with a phone-number second line (own row, COL_GUEST,
    # matched against PHONE_RE = ^\(\d{3}\)$ on the first token).
    _draw_row(c, 150, "6:00", 2, "Emma Depp", ["artisans, STLWTR"], phone="(518) 524-3417")

    # 3. Multi-line Notes & Tags -- keeps stacking under COL_NOTES until the
    # next Time-column row starts.
    _draw_row(c, 178, "6:30", 4, "HANKS", ["artisans 3 rooms VVIP", "comp dinner. EK"])

    # 4. Outside guest -- no in-house room hint at all.
    _draw_row(c, 210, "8:00", 2, "bill jennings", ["artisans off property", "no allergies"])

    # ---- Footer (ignored by fixed-phrase match) ---------------------------
    top = 700
    c.setFont("Helvetica", 7)
    c.setFillColor(HexColor("#6B7280"))
    footer_text = "About  Discover  Languages  Get the Yelp for Business app  Content Guidelines  Copyright (C) Yelp Inc.  biz.yelp.com"
    c.drawString(40, _top_to_y(top), footer_text)
    if annotated:
        _draw_ignored_band(c, 20, 560, top - 3, top + 12, "IGNORED: footer (matched by fixed phrase list, e.g. 'Copyright')")

        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(HexColor("#111827"))
        c.drawString(40, 40, "Blue = parsed by column position (x0 band).  Gray = ignored (text/position match).")


def build_annotated_yelp_replica(path: str) -> None:
    """Same replica page with colored column-band boxes + labels overlaid,
    so it's visible which pixels the parser reads for each field."""
    c = canvas.Canvas(path, pagesize=letter)
    _draw_shared_content(c, annotated=True)
    c.showPage()
    c.save()


def build_clean_yelp_replica(path: str) -> None:
    """Same replica page with no annotation boxes/labels -- just the plain
    realistic-looking content, like a real Yelp for Business PDF print."""
    c = canvas.Canvas(path, pagesize=letter)
    _draw_shared_content(c, annotated=False)
    c.showPage()
    c.save()


if __name__ == "__main__":
    build_annotated_yelp_replica("tests_synthetic/sample_output/annotated_yelp_replica.pdf")
    print("wrote tests_synthetic/sample_output/annotated_yelp_replica.pdf")
    build_clean_yelp_replica("tests_synthetic/sample_output/clean_yelp_replica.pdf")
    print("wrote tests_synthetic/sample_output/clean_yelp_replica.pdf")
