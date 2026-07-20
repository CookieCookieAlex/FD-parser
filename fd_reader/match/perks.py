"""Detect perk call-outs (Virtuoso, breakfast-included) from a guest's raw
note text. These aren't reservation-matching signals -- they're a data-
quality/informational scan over the same three free-text fields used
elsewhere (guest_notes / reservation_notes / comments_notes), per
CLAUDE.md's "there are three separate free-text note fields" guidance.
Real examples seen in the sample PDFs (see SESSION_HISTORY.md):

  "BREAKFAST INCLUDED VIRTUOSO...$100.00 VIRTUOSO CREDIT...WELCOME LETTER..."
  "Breakfast included Virtuoso, $100 Virtuoso credit at checkout."
  "BREAKFAST INCLLUDED VIRTUOSO..." (real typo in the source data)

Both phrases showed up exclusively in Reservation Notes in the samples, but
nothing guarantees that in general -- scan all three fields.
"""
from __future__ import annotations

import re

from fd_reader.match.notes_cross_check import NOTE_FIELDS
from fd_reader.models import GuestRecord

VIRTUOSO_RE = re.compile(r"virtuoso", re.IGNORECASE)
# Tolerate the real "INCLLUDED" typo seen in the sample data by matching on
# "BREAKFAST" + "INCLU/INCLL" rather than requiring an exact word.
BREAKFAST_RE = re.compile(r"breakfast\s+incl\w*", re.IGNORECASE)


def _all_notes_text(guest: GuestRecord) -> str:
    return " ".join(getattr(guest, field) or "" for field in NOTE_FIELDS)


def is_virtuoso(guest: GuestRecord) -> bool:
    return bool(VIRTUOSO_RE.search(_all_notes_text(guest)))


def is_breakfast_included(guest: GuestRecord) -> bool:
    return bool(BREAKFAST_RE.search(_all_notes_text(guest)))
