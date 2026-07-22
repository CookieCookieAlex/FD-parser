from fd_reader.match.capacity_check import check_capacity
from fd_reader.match.perks import is_pet_amenities
from fd_reader.models import GuestRecord


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


def test_under_capacity_is_not_flagged():
    guest = _guest(room_name="PLACID", guests_count=3)  # Lakeside max is 3
    assert check_capacity(guest) is None


def test_over_capacity_lakeside_room_is_flagged():
    guest = _guest(room_name="PLACID", guests_count=4)  # Lakeside max is 3
    check = check_capacity(guest)
    assert check is not None
    assert check.max_guests == 3
    assert check.actual_guests == 4


def test_over_capacity_single_king_room_is_flagged():
    guest = _guest(room_name="PINE", guests_count=3)  # Overlook single-king max is 2
    check = check_capacity(guest)
    assert check is not None
    assert check.max_guests == 2
    assert check.actual_guests == 3


def test_buck_allows_up_to_five():
    guest = _guest(room_name="BUCK", guests_count=5)
    assert check_capacity(guest) is None
    guest = _guest(room_name="BUCK", guests_count=6)
    check = check_capacity(guest)
    assert check is not None
    assert check.max_guests == 5


def test_kiwassa_and_lookout_allow_up_to_four():
    for room in ("KIWA", "LOOK"):
        guest = _guest(room_name=room, guests_count=4)
        assert check_capacity(guest) is None, room
        guest = _guest(room_name=room, guests_count=5)
        check = check_capacity(guest)
        assert check is not None, room
        assert check.max_guests == 4


def test_mt_jo_has_no_sofa_so_max_is_two():
    guest = _guest(room_name="MTJO", guests_count=3)
    check = check_capacity(guest)
    assert check is not None
    assert check.max_guests == 2


def test_unknown_room_is_not_flagged():
    guest = _guest(room_name="NOT-A-REAL-ROOM", guests_count=99)
    assert check_capacity(guest) is None


def test_missing_guests_count_is_not_flagged():
    guest = _guest(room_name="PLACID", guests_count=None)
    assert check_capacity(guest) is None


def test_missing_room_name_is_not_flagged():
    guest = _guest(room_name="", guests_count=10)
    assert check_capacity(guest) is None


def test_pet_amenities_detected_from_real_sample_phrasing():
    guest = _guest(reservation_notes="PET AMENITIES FOR RETIRED GUIDE DOG...")
    assert is_pet_amenities(guest)


def test_pet_friendly_phrasing_detected():
    guest = _guest(guest_notes="no allergies noted , pet friendly rm requstd")
    assert is_pet_amenities(guest)


def test_no_pet_mention_not_flagged():
    guest = _guest(reservation_notes="BREAKFAST INCLUDED VIRTUOSO...")
    assert not is_pet_amenities(guest)
