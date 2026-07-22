from fd_reader.match.perks import is_breakfast_included, is_virtuoso
from fd_reader.models import GuestRecord


def _guest(**overrides) -> GuestRecord:
    base = dict(
        confirmation_number="1-1",
        guest_name="Jackson, John",
        room_name="ROOM",
        room_type="TYPE",
        status="Reserved",
        arrival_date="06/28/2026",
        departure_date="06/29/2026",
        guests_count=2,
        guests_share=0,
        source_page=1,
    )
    base.update(overrides)
    return GuestRecord(**base)


def test_virtuoso_detected_case_insensitive():
    guest = _guest(reservation_notes="BREAKFAST INCLUDED VIRTUOSO...$100.00 VIRTUOSO CREDIT...")
    assert is_virtuoso(guest)
    assert is_breakfast_included(guest)


def test_virtuoso_lowercase_in_comments_notes():
    guest = _guest(comments_notes="apply virtuoso credit at checkout")
    assert is_virtuoso(guest)
    assert not is_breakfast_included(guest)


def test_breakfast_included_typo_tolerated():
    """Real sample data has the typo 'BREAKFAST INCLLUDED' -- must still match."""
    guest = _guest(reservation_notes="BREAKFAST INCLLUDED VIRTUOSO...")
    assert is_breakfast_included(guest)


def test_breakfast_included_in_guest_notes_field():
    guest = _guest(guest_notes="Breakfast included as part of package.")
    assert is_breakfast_included(guest)
    assert not is_virtuoso(guest)


def test_neither_perk_present():
    guest = _guest(reservation_notes="REPEAT GUESTS...4TH VISIT...WELCOME LETTER...")
    assert not is_virtuoso(guest)
    assert not is_breakfast_included(guest)


def test_empty_notes_no_crash():
    guest = _guest()
    assert not is_virtuoso(guest)
    assert not is_breakfast_included(guest)
