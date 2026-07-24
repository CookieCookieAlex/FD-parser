"""Shared word/row extraction for pdfplumber pages.

Both source PDFs (the arrivals report and the Yelp reservations printout)
are parsed the same way: pull words with coordinates, sort them, and group
words on the same printed line into a `Row`. Each parser then reads its own
x0 column bands off of `Row` -- see parsing/guests/rows.py and
parsing/reservations/rows.py for the per-document specifics.
"""
from __future__ import annotations

from dataclasses import dataclass

# Row grouping tolerance: words on the same printed line can differ in
# `top` by a point or two due to font metrics.
ROW_TOP_TOLERANCE = 2.0


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Row:
    words: list[Word]
    top: float

    def text_in_range(self, x0: float | None = None, x1: float | None = None) -> str:
        selected = [
            w
            for w in self.words
            if (x0 is None or w.x0 >= x0) and (x1 is None or w.x0 < x1)
        ]
        return " ".join(w.text for w in selected)

    def text_in(self, band: tuple[float, float]) -> str:
        return self.text_in_range(x0=band[0], x1=band[1])

    def words_in(self, band: tuple[float, float]) -> list[Word]:
        return [w for w in self.words if band[0] <= w.x0 < band[1]]


def extract_rows(page) -> list[Row]:
    words = [
        Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
        for w in page.extract_words(use_text_flow=False, keep_blank_chars=False)
    ]
    words.sort(key=lambda w: (w.top, w.x0))

    rows: list[Row] = []
    for w in words:
        if rows and abs(w.top - rows[-1].top) <= ROW_TOP_TOLERANCE:
            rows[-1].words.append(w)
        else:
            rows.append(Row(words=[w], top=w.top))
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows
