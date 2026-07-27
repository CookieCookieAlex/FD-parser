import os
import tempfile

from fd_reader.match.pet_room_check import check_pet_room
from fd_reader.models import GuestRecord
from fd_reader.parsing.guests import parse_guest_pdf
from tests_synthetic.pdf_writer import build_synthetic_arrivals_pdf


def _guest(**overrides) -> GuestRecord:
    base = dict(
        confirmation_number="1-1",
        guest_name="Jackson, John",
        room_name="PLACID",
        room_type="LU1KF",
        status="Reserved",
        arrival_date="06/28/2026",
        departure_date="06/29/2026",
        guests_count=2,
        guests_share=0,
        source_page=1,
    )
    base.update(overrides)
    return GuestRecord(**base)


def test_no_pet_mention_returns_none():
    guest = _guest(room_name="TAMAR")  # not a cabin, but no pet mentioned
    assert check_pet_room(guest) is None


def test_pet_amenities_in_cabin_is_allowed():
    guest = _guest(room_name="BUCK", comments_notes="PET AMENITIES requested for small dog.")
    assert check_pet_room(guest) is None


def test_pet_amenities_in_non_cabin_room_is_flagged():
    guest = _guest(room_name="TAMAR", comments_notes="PET AMENITIES FOR RETIRED GUIDE DOG")
    check = check_pet_room(guest)
    assert check is not None
    assert check.room_category == "Main Lodge"


def test_pet_friendly_phrasing_detected():
    guest = _guest(room_name="PINE", guest_notes="Guest is pet friendly, bringing a small dog.")
    check = check_pet_room(guest)
    assert check is not None
    assert check.room_category == "Overlook"


def test_lakeside_room_is_not_a_cabin():
    guest = _guest(room_name="RAQTTE", reservation_notes="PET AMENITIES for the stay.")
    check = check_pet_room(guest)
    assert check is not None
    assert check.room_category == "Lakeside"


def test_unknown_room_is_not_flagged():
    guest = _guest(room_name="NOT-A-REAL-ROOM", guest_notes="PET AMENITIES requested.")
    assert check_pet_room(guest) is None


def test_missing_room_name_is_not_flagged():
    guest = _guest(room_name="", guest_notes="PET AMENITIES requested.")
    assert check_pet_room(guest) is None


def test_unrelated_note_text_not_flagged():
    guest = _guest(room_name="TAMAR", reservation_notes="BREAKFAST INCLLUDED VIRTUOSO...$100.00")
    assert check_pet_room(guest) is None


# --- Real PDF, not a hand-built GuestRecord -- catches parser-layer gaps
# that unit tests above (which build GuestRecord directly) can't see, e.g.
# note text failing to reach the parsed record at all. ------------------


def test_pet_amenities_survives_real_pdf_parsing_and_page_break():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, "arrivals.pdf")
        build_synthetic_arrivals_pdf(pdf_path)
        records = parse_guest_pdf(pdf_path)

    # "PET AMENITIES FOR RETIRED GUIDE DOG" continues Cyrus, Sophia's
    # Comments/Notes across a page break -- she's in TAMAR (Main Lodge,
    # not a Cabin). The wording itself is never inspected for "service"/
    # "guide" -- any pet-amenities mention in a non-Cabin room is flagged
    # the same way, and it's on staff to verify service-dog status.
    cyrus = next(r for r in records if r.guest_name == "Cyrus, Sophia")
    check = check_pet_room(cyrus)
    assert check is not None
    assert check.room_category == "Main Lodge"
