"""Regression tests for fd_reader.parsing.notes, pinned against real note
strings from guest-notes/arrival_notes.pdf and
guest-notes/arrivals-notes-6days-advance.pdf (see SESSION_HISTORY.md
session 4). Covers both note styles seen in real data: explicit-date
notes (mixed case) and weekday-only notes (ALL CAPS, one staff member's
style, needs the guest's stay window to resolve to an actual date).
"""
from datetime import date

from fd_reader.parsing.notes import extract_note_mentions


def test_explicit_date_note():
    mentions = extract_note_mentions(
        "Maggie's 6/30 @ 7PM", "comments_notes", "06/28/2026", "07/01/2026"
    )
    assert len(mentions) == 1
    m = mentions[0]
    assert m.restaurant == "Maggie's"
    assert m.resolved_date == date(2026, 6, 30)
    assert m.time_text == "7PM"
    assert m.flags == []


def test_two_mentions_comma_separated_explicit_dates():
    mentions = extract_note_mentions(
        "Artisans 6/29 @ 7PM, Maggie's 7/1 @ 6:30",
        "comments_notes",
        "06/29/2026",
        "07/02/2026",
    )
    assert len(mentions) == 2
    assert mentions[0].restaurant == "Artisans"
    assert mentions[0].resolved_date == date(2026, 6, 29)
    assert mentions[1].restaurant == "Maggie's"
    assert mentions[1].resolved_date == date(2026, 7, 1)


def test_weekday_only_note_resolves_using_stay_window():
    """The all-caps staff member's style -- no date at all, must be
    resolved from [arrival, departure)."""
    mentions = extract_note_mentions(
        "REPEAT GUESTS...2ND VISIT...WELCOME LETTER...TUESDAY MAGGIES 6PM, "
        "WEDNESDAY ARTISANS 6PM...",
        "reservation_notes",
        "06/30/2026",
        "07/02/2026",
    )
    by_restaurant = {m.restaurant: m for m in mentions}
    assert by_restaurant["Maggie's"].resolved_date == date(2026, 6, 30)  # Tuesday
    assert by_restaurant["Artisans"].resolved_date == date(2026, 7, 1)  # Wednesday
    assert all(not m.flags for m in mentions)


def test_weekday_only_note_multiple_mentions_thursday_sunday():
    mentions = extract_note_mentions(
        "ROOM MOVE FROM AUSABLE...THURSDAY ARTISANS 7:00PM, SUNDAY MAGGIES 6:00PM...",
        "reservation_notes",
        "07/01/2026",
        "07/06/2026",
    )
    by_restaurant = {m.restaurant: m for m in mentions}
    assert by_restaurant["Artisans"].resolved_date == date(2026, 7, 2)  # Thursday
    assert by_restaurant["Maggie's"].resolved_date == date(2026, 7, 5)  # Sunday


def test_ambiguous_weekday_flagged_not_guessed():
    """Kosloske's real 12-night stay (06/23-07/05) contains both Fridays
    and both Saturdays -- FRIDAY/SATURDAY cannot resolve to one date and
    must be flagged, not guessed."""
    mentions = extract_note_mentions(
        "FRIDAY ARTISANS 7PM, SATURDAY MAGGIES 7PM, SATURDAY ARTISANS 7PM...",
        "reservation_notes",
        "06/23/2026",
        "07/05/2026",
    )
    assert len(mentions) == 3
    for m in mentions:
        assert m.resolved_date is None
        assert m.is_ambiguous_weekday is True
        assert "ambiguous_weekday" in m.flags
    assert mentions[0].candidate_dates == [date(2026, 6, 26), date(2026, 7, 3)]  # both Fridays
    assert mentions[1].candidate_dates == [date(2026, 6, 27), date(2026, 7, 4)]  # both Saturdays


def test_same_month_two_day_range_with_ampersand_bare_day():
    """'Artisans on 06/25 & 26 @ 7PM' means two separate reservations
    (6/25 AND 6/26), not one mention with a typo -- must emit both."""
    mentions = extract_note_mentions(
        "Artisans on 06/25 & 26 @ 7PM", "reservation_notes", "06/25/2026", "06/27/2026"
    )
    assert len(mentions) == 2
    assert {m.resolved_date for m in mentions} == {date(2026, 6, 25), date(2026, 6, 26)}
    assert all(m.restaurant == "Artisans" for m in mentions)


def test_same_month_two_day_range_with_ampersand_full_date():
    """'7/3 & 7/4-maggies @ 7pm 2ppl' -- second day given as a full M/D,
    not a bare day number; must not mis-truncate to '& 7'."""
    mentions = extract_note_mentions(
        "7/3 & 7/4-maggies @ 7pm 2ppl", "comments_notes", "07/03/2026", "07/06/2026"
    )
    assert len(mentions) == 2
    assert {m.resolved_date for m in mentions} == {date(2026, 7, 3), date(2026, 7, 4)}


def test_spelled_month_with_redundant_weekday():
    """'June 26th-Thursday- Artisans @ 8Pm 4 ppl' -- explicit spelled date
    takes priority; the weekday is redundant/self-checking, not needed to
    resolve the date."""
    mentions = extract_note_mentions(
        "June 26th-Thursday- Artisans @ 8Pm 4 ppl",
        "comments_notes",
        "06/25/2026",
        "06/27/2026",
    )
    assert len(mentions) == 1
    assert mentions[0].resolved_date == date(2026, 6, 26)
    assert mentions[0].weekday_text == "THURSDAY"


def test_no_restaurant_mention_returns_empty():
    mentions = extract_note_mentions(
        "PET AMENITIES FOR RETIRED GUIDE DOG...", "guest_notes", "07/03/2026", "07/06/2026"
    )
    assert mentions == []


def test_empty_note_returns_empty():
    assert extract_note_mentions("", "guest_notes", "07/03/2026", "07/06/2026") == []
    assert extract_note_mentions(None, "guest_notes", "07/03/2026", "07/06/2026") == []


def test_three_way_weekday_note_kosloske_style_unambiguous_stay():
    """Same weekday-list pattern as Kosloske but over a short (non-
    ambiguous) stay window should resolve cleanly, confirming the
    ambiguity is about stay length, not the note format itself."""
    mentions = extract_note_mentions(
        "FRIDAY ARTISANS 7PM, SATURDAY MAGGIES 7PM",
        "reservation_notes",
        "07/02/2026",
        "07/05/2026",
    )
    by_restaurant = {m.restaurant: m for m in mentions}
    assert by_restaurant["Artisans"].resolved_date == date(2026, 7, 3)  # Friday
    assert by_restaurant["Maggie's"].resolved_date == date(2026, 7, 4)  # Saturday
    assert all(not m.flags for m in mentions)
