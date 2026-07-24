import os
import tempfile

from fd_reader.match.sofa_bed_check import check_sofa_bed, requests_sofa_bed
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


def test_no_mention_returns_none():
    guest = _guest(room_name="PLACID")  # has a sofa bed, but never requested
    assert check_sofa_bed(guest) is None
    assert not requests_sofa_bed(guest)


def test_request_in_room_with_sofa_bed_is_satisfied():
    guest = _guest(room_name="PLACID", comments_notes="Guest requested a sofa bed for their child.")
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is True


def test_request_in_room_without_sofa_bed_is_unsatisfied():
    guest = _guest(room_name="MTJO", guest_notes="Requesting sofa bed if possible.")  # Mt. Jo has no sofa
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is False


def test_pull_out_phrasing_detected():
    guest = _guest(room_name="MTJO", reservation_notes="Needs a pull-out for extra guest.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is False


def test_sleeper_sofa_phrasing_detected():
    guest = _guest(room_name="BUCK", comments_notes="Would like the sleeper sofa made up.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is True


def test_kiwassa_and_lookout_have_no_sofa_despite_higher_capacity():
    # Kiwassa/Lookout sleep 4 via two kings, not a sofa -- distinct from
    # rooms with the same/higher max_guests that DO have one (see
    # rooms/directory.py's has_sofa_bed docstring).
    for room in ("KIWA", "LOOK"):
        guest = _guest(room_name=room, guest_notes="sofa bed please")
        check = check_sofa_bed(guest)
        assert check is not None, room
        assert check.satisfied is False, room


def test_unrelated_note_text_not_flagged():
    guest = _guest(reservation_notes="BREAKFAST INCLUDED VIRTUOSO...$100.00 VIRTUOSO CREDIT...")
    assert not requests_sofa_bed(guest)
    assert check_sofa_bed(guest) is None


def test_rollaway_phrasing_detected():
    guest = _guest(room_name="MTJO", comments_notes="Please add a rollaway bed for the kid.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is False


def test_rollaway_no_hyphen_or_space_variant_detected():
    guest = _guest(room_name="MTJO", comments_notes="Requesting a roll away.")
    assert requests_sofa_bed(guest)


def test_extra_bed_phrasing_detected():
    guest = _guest(room_name="MTJO", guest_notes="Guest needs an extra bed in the room.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is False


def test_additional_bed_phrasing_detected():
    guest = _guest(room_name="PLACID", reservation_notes="Additional bed requested for the stay.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is True


def test_foldout_phrasing_detected():
    guest = _guest(room_name="MTJO", comments_notes="Fold-out couch needed please.")
    assert requests_sofa_bed(guest)


def test_cot_phrasing_detected():
    guest = _guest(room_name="MTJO", guest_notes="Please set up a cot in the room.")
    assert requests_sofa_bed(guest)
    check = check_sofa_bed(guest)
    assert check is not None
    assert check.satisfied is False


def test_cots_plural_detected():
    guest = _guest(room_name="MTJO", comments_notes="Family needs two cots for the kids.")
    assert requests_sofa_bed(guest)


def test_cot_does_not_false_positive_inside_other_words():
    guest = _guest(comments_notes="Guest's last name is Scott, staying at the cottage next door as a mascot.")
    assert not requests_sofa_bed(guest)


def test_bare_bed_or_couch_mention_not_flagged():
    # "bed"/"couch" alone are deliberately too broad to match on their own.
    guest = _guest(comments_notes="Guest loves the comfortable bed and the couch by the window.")
    assert not requests_sofa_bed(guest)


def test_unknown_room_is_not_flagged():
    guest = _guest(room_name="NOT-A-REAL-ROOM", guest_notes="sofa bed requested")
    assert check_sofa_bed(guest) is None


def test_missing_room_name_is_not_flagged():
    guest = _guest(room_name="", guest_notes="sofa bed requested")
    assert check_sofa_bed(guest) is None


# --- Real PDF, not a hand-built GuestRecord -- catches parser-layer gaps
# that unit tests above (which build GuestRecord directly) can't see, e.g.
# note text failing to reach the parsed record at all. ------------------


def test_sofa_bed_request_survives_real_pdf_parsing_satisfied_case():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, "arrivals.pdf")
        build_synthetic_arrivals_pdf(pdf_path)
        records = parse_guest_pdf(pdf_path)

    turner = next(r for r in records if r.guest_name == "Turner, Grace")
    assert requests_sofa_bed(turner)
    check = check_sofa_bed(turner)
    assert check is not None
    assert check.satisfied is True  # RAQTTE (Lakeside) has a sofa bed


def test_sofa_bed_request_survives_real_pdf_parsing_unsatisfied_case():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, "arrivals.pdf")
        build_synthetic_arrivals_pdf(pdf_path)
        records = parse_guest_pdf(pdf_path)

    wilson = next(r for r in records if r.guest_name == "Wilson, Henry")
    assert requests_sofa_bed(wilson)
    check = check_sofa_bed(wilson)
    assert check is not None
    assert check.satisfied is False  # TAMAR (Main Lodge) has no sofa bed
