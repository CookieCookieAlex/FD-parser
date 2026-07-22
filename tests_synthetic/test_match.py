"""Regression tests for fd_reader.match using entirely synthetic
GuestRecord/ReservationRecord data -- no real guest-notes/ PDFs involved.
Covers the same structural cases documented in CLAUDE.md and previously
pinned against real sample data (room-code mismatch flagged not silently
trusted, outside guests never matched, same-surname vs exact-name group
bookings, room moves, notes/Yelp cross-check mismatches) but with made-up
guests (see tests_synthetic/fixtures.py).
"""
from datetime import date

from fd_reader.match import cross_check_notes, detect_room_moves, find_room_groups, match_reservations
from fd_reader.match._dates import parse_source_date

from tests_synthetic.fixtures import make_guest, make_reservation


def by_guest_reservation(results, name_substring):
    return [
        r for r in results
        if name_substring.lower() in r.reservation.guest_name.lower()
    ]


# --- parse_source_date --------------------------------------------------


def test_parse_source_date_accepts_abbreviated_month():
    assert parse_source_date("Jun 20, 2026") == date(2026, 6, 20)


def test_parse_source_date_accepts_full_month_name():
    """The filter-bar extraction regex (_find_date_from_filter_bar) captures
    the month token generically (\\w+), so it would happily capture a full
    month name like 'June' if Yelp ever renders one that way -- the parser
    must accept it too, not silently fail every reservation in that day's
    file just because the abbreviation was expected."""
    assert parse_source_date("June 29, 2026") == date(2026, 6, 29)
    assert parse_source_date("July 15, 2026") == date(2026, 7, 15)


def test_parse_source_date_returns_none_for_garbage():
    assert parse_source_date("not a date") is None
    assert parse_source_date("") is None


def test_full_month_name_reservation_still_matches_a_guest():
    """Integration-level version of the unit test above: if a Yelp file's
    filter bar ever spells out the month in full, a reservation from that
    file must still resolve normally -- not silently fall into
    'unparseable_reservation_date' with guest=None for every row."""
    guest = make_guest(
        confirmation_number="S-1", guest_name="Jackson, John",
        arrival_date="06/29/2026", departure_date="07/02/2026",
    )
    reservation = make_reservation(
        guest_name="John Jackson", source_date="June 29, 2026",
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest], [reservation])
    assert len(results) == 1
    assert results[0].guest is guest
    assert "unparseable_reservation_date" not in results[0].flags


# --- match_reservations -----------------------------------------------


def test_name_match_resolves_and_flags_room_mismatch():
    """Reservation's room-code hint disagrees with the guest's real room --
    name still resolves the match; room is a secondary confirm signal that
    must flag the disagreement, not silently trust either field."""
    guest = make_guest(
        confirmation_number="A-1", guest_name="Jackson, John",
        room_name="LOOK", arrival_date="07/10/2026", departure_date="07/12/2026",
    )
    reservation = make_reservation(
        guest_name="John Jackson", source_date="Jul 10, 2026",
        notes_tags="artisans KIWA", room_code_hint="s KIWA",
    )
    results = match_reservations([guest], [reservation])
    assert len(results) == 1
    assert results[0].match_method == "name"
    assert results[0].guest is guest
    assert "room_mismatch" in results[0].flags


def test_outside_guest_never_matched():
    guest = make_guest(confirmation_number="B-1", guest_name="Sheeran, Steve")
    reservation = make_reservation(
        guest_name="steve sheeran off property", source_date="Jul 10, 2026",
        is_outside_guest=True, notes_tags="artisans off property no allergies",
    )
    results = match_reservations([guest], [reservation])
    assert len(results) == 1
    assert results[0].guest is None
    assert "outside_guest" in results[0].flags


def test_ambiguous_name_match_attaches_to_top_candidate_and_lists_others():
    """Two unrelated guests with the same surname on the same night (
    different rooms/stays, not a family group) -- reservation has no room
    hint and neither guest's notes mention a matching time, so it can't be
    disambiguated. Rather than vanishing from the report (guest=None), it
    must attach to a candidate so it's visible somewhere, stay flagged
    ambiguous, and list the other plausible guest(s)."""
    guest_1 = make_guest(
        confirmation_number="C-1", guest_name="Depp, Emma", room_name="PINEVW",
        arrival_date="07/10/2026", departure_date="07/12/2026",
    )
    guest_2 = make_guest(
        confirmation_number="C-2", guest_name="Depp, Olivia", room_name="BUCK",
        arrival_date="07/09/2026", departure_date="07/15/2026",
    )
    reservation = make_reservation(
        guest_name="DEPP", source_date="Jul 10, 2026",
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest_1, guest_2], [reservation])
    assert len(results) == 1
    assert results[0].guest in (guest_1, guest_2)
    assert "ambiguous_name_match" in results[0].flags
    assert results[0].other_candidates == [g for g in (guest_1, guest_2) if g is not results[0].guest]


def test_ambiguous_name_match_resolved_by_matching_note_time():
    """Same tie as above, but one of the two candidates has a note that
    names this restaurant/date with a time matching the reservation --
    that's enough to resolve the tie (flagged differently, so it's clear
    this was inferred rather than a clean name match)."""
    guest_1 = make_guest(
        confirmation_number="C-1", guest_name="Depp, Emma", room_name="PINEVW",
        arrival_date="07/10/2026", departure_date="07/12/2026",
        comments_notes="Artisans 7/10 @ 7PM",
    )
    guest_2 = make_guest(
        confirmation_number="C-2", guest_name="Depp, Olivia", room_name="BUCK",
        arrival_date="07/09/2026", departure_date="07/15/2026",
    )
    reservation = make_reservation(
        guest_name="DEPP", source_date="Jul 10, 2026", time="7:00",
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest_1, guest_2], [reservation])
    assert len(results) == 1
    assert results[0].guest is guest_1
    assert "resolved_by_note_time" in results[0].flags
    assert results[0].other_candidates == [guest_2]


def test_different_first_name_same_surname_does_not_false_match():
    """Regression test: a Yelp row with a full name (first + last) that
    shares a surname with an in-house guest, but has a DIFFERENT first
    name, must score well below the match threshold -- it must never be
    treated as the same person just because the surname matches.

    This was a real bug: _name_variants used to always emit a
    surname-only comparison form for every name, which let two entirely
    different people sharing a surname (e.g. Yelp rows "Kate Hopkins" and
    "Grace Hopkins") both score a perfect 100 against one guest "Hopkins,
    Grace" -- the surname-only comparison silently discarded both first
    names and that inflated score beat the correctly low full-name
    comparison. Confirmed via a real reproduction: a deliberate note/Yelp
    mismatch test case (guest's note says Artisans, her real Yelp
    reservation is at Maggie's) got silently absorbed as 'matched'
    instead of 'mismatch', because an unrelated randomly-generated
    same-surname Yelp reservation (different first name) was incorrectly
    treated as equally valid and grabbed by the note-matching logic
    first."""
    guest = make_guest(
        confirmation_number="C0-1", guest_name="Hopkins, Grace",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    wrong_person = make_reservation(
        guest_name="Kate Hopkins", source_date="Jul 11, 2026",
        notes_tags="artisans", room_code_hint=None,
    )
    right_person = make_reservation(
        guest_name="Grace Hopkins", source_date="Jul 11, 2026",
        notes_tags="maggie's", room_code_hint=None,
    )

    results = match_reservations([guest], [wrong_person, right_person])
    assert len(results) == 2

    wrong_result = next(r for r in results if r.reservation.guest_name == "Kate Hopkins")
    assert wrong_result.guest is None
    assert "no_match_found" in wrong_result.flags

    right_result = next(r for r in results if r.reservation.guest_name == "Grace Hopkins")
    assert right_result.guest is guest
    assert right_result.match_method == "name"


def test_surname_only_resolves_via_linked_group():
    """Surname-only Yelp row ties across a linked room-group (one family,
    multiple rooms) -- not a real ambiguity, should resolve with the other
    rooms carried in linked_group."""
    rooms = [
        make_guest(
            confirmation_number=f"D-{i}", guest_name="Hanks, Laura",
            room_name=room, arrival_date="07/10/2026", departure_date="07/13/2026",
        )
        for i, room in enumerate(["TAHAW", "AMPER", "MTJO"], start=1)
    ]
    reservation = make_reservation(
        guest_name="HANKS", source_date="Jul 10, 2026",
        notes_tags="artisans 3 rooms", room_code_hint=None,
    )
    results = match_reservations(rooms, [reservation])
    assert len(results) == 1
    assert results[0].guest is not None
    assert "ambiguous_name_match" not in results[0].flags
    assert len(results[0].linked_group) == 2


def test_party_size_mismatch_flagged():
    guest = make_guest(confirmation_number="E-1", guest_name="Swift, Michael", guests_count=2)
    reservation = make_reservation(
        guest_name="Michael Swift", source_date="Jul 10, 2026", party_size=4,
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest], [reservation])
    assert "party_size_mismatch" in results[0].flags


def test_full_name_match_no_room_hint_flagged_yellow_not_red():
    """Full first+last name match, in-house dates line up, but Notes &
    Tags has no resolvable room hint at all -- a real identifying signal
    (the full name) is present, so this is a softer 'no_room_hint' issue,
    not the surname-only ambiguity risk below."""
    guest = make_guest(
        confirmation_number="R-1", guest_name="Hopkins, Grace", room_name="AUSABL",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    reservation = make_reservation(
        guest_name="Grace Hopkins", source_date="Jul 11, 2026",
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest], [reservation])
    assert results[0].guest is guest
    assert "no_room_hint" in results[0].flags
    assert "surname_only_no_room_hint" not in results[0].flags


def test_surname_only_no_room_hint_flagged_as_potential_outside_guest():
    """A bare surname (no first name at all, e.g. real Yelp rows like
    'HANKS') with no resolvable room hint either -- the ONLY thing tying
    this reservation to a specific in-house guest is a last name. That's a
    real risk of confusing an unrelated person (never a guest here) who
    happens to share a surname with someone in-house, so this must be
    flagged distinctly (and more severely) than the full-name case above,
    per user direction -- confirmed this exact collision happened once
    with synthetic data (two different real full names, 'Grace Hopkins'
    and 'Kate Hopkins', both scoring 100 against one guest via the
    surname-only fallback) before _best_name_score was fixed to stop
    letting a bare-surname score override a worse full-name score."""
    guest = make_guest(
        confirmation_number="R-2", guest_name="Hanks, Laura", room_name="TAHAW",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    reservation = make_reservation(
        guest_name="HANKS", source_date="Jul 11, 2026",
        notes_tags="artisans", room_code_hint=None,
    )
    results = match_reservations([guest], [reservation])
    assert results[0].guest is guest
    assert "surname_only_no_room_hint" in results[0].flags
    assert "no_room_hint" not in results[0].flags


def test_surname_only_with_room_hint_not_flagged():
    """Surname-only match, but the room hint DOES resolve and agree with
    the guest's actual room -- enough corroborating signal that this
    should NOT get the potential-outside-guest flag."""
    guest = make_guest(
        confirmation_number="R-3", guest_name="Hanks, Laura", room_name="TAHAW",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    reservation = make_reservation(
        guest_name="HANKS", source_date="Jul 11, 2026",
        notes_tags="artisans TAHAW", room_code_hint="TAHAW",
    )
    results = match_reservations([guest], [reservation])
    assert "surname_only_no_room_hint" not in results[0].flags
    assert "no_room_hint" not in results[0].flags


def test_two_different_full_names_same_surname_do_not_collide():
    """Regression test for the exact bug found during development: two
    DIFFERENT real full names sharing a surname (e.g. 'Grace Hopkins' and
    'Kate Hopkins') must NOT both score a perfect match against one guest
    just because their surnames agree -- the full-name comparison must
    win over the surname-only fallback whenever a first name is actually
    given on the Yelp side."""
    guest = make_guest(
        confirmation_number="R-4", guest_name="Hopkins, Grace",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    matching_reservation = make_reservation(
        guest_name="Grace Hopkins", source_date="Jul 11, 2026", notes_tags="artisans",
    )
    other_person_reservation = make_reservation(
        guest_name="Kate Hopkins", source_date="Jul 11, 2026", notes_tags="artisans",
    )
    results = match_reservations([guest], [matching_reservation, other_person_reservation])

    grace_result = next(r for r in results if r.reservation.guest_name == "Grace Hopkins")
    kate_result = next(r for r in results if r.reservation.guest_name == "Kate Hopkins")

    assert grace_result.guest is guest
    assert grace_result.confidence == 100
    # "Kate Hopkins" has a real first name that disagrees with "Grace" --
    # must NOT tie with the exact match (the original bug: both scored
    # 100 via the surname-only fallback). It scores low enough to miss
    # the match threshold entirely here, which is the correct, even
    # stronger outcome: Kate is never silently attached to Grace's record.
    assert kate_result.guest is None
    assert kate_result.confidence is None


def test_same_first_name_different_surname_never_matches():
    """Regression test for a second, related real bug found during
    development: 'Laura Hanks' (guest) vs 'Laura Adams' (a totally
    different person, unrelated Yelp reservation) scored 75 -- above
    FUZZY_NAME_THRESHOLD -- purely because the shared first name kept
    fuzz.token_sort_ratio's combined-string score high, even though the
    surnames ('hanks' vs 'adams') barely agree at all. Confirmed to
    silently attach an unrelated guest's reservation to Laura Hanks' card
    in testing. Per user direction: a shared first name must never be
    enough to carry a match when the surnames don't independently agree --
    first names are common across many guests and are a much weaker
    signal than surnames."""
    guest = make_guest(
        confirmation_number="R-5", guest_name="Hanks, Laura",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    unrelated_reservation = make_reservation(
        guest_name="Laura Adams", source_date="Jul 11, 2026", notes_tags="artisans",
    )
    results = match_reservations([guest], [unrelated_reservation])
    assert results[0].guest is None
    assert "no_match_found" in results[0].flags


def test_same_surname_different_first_name_never_matches():
    """Regression test for a third, symmetric bug found during
    development: 'Cyrus, Sophia' (guest) vs 'John Cyrus'/'Tom
    Cyrus'/'Leo Cyrus' (different, unrelated people who genuinely share
    the surname) all scored above FUZZY_NAME_THRESHOLD once the surname
    gate passed (the surname really does agree), because the combined
    full-name string stayed deceptively similar even with a totally
    different first name. Per user direction: a matching surname alone
    must never be enough either -- the first names must also
    independently agree, symmetric to the surname-agreement gate."""
    guest = make_guest(
        confirmation_number="R-6", guest_name="Cyrus, Sophia",
        arrival_date="07/06/2026", departure_date="07/18/2026",
    )
    unrelated_reservations = [
        make_reservation(guest_name="John Cyrus", source_date="Jul 10, 2026", notes_tags="artisans"),
        make_reservation(guest_name="Tom Cyrus", source_date="Jul 10, 2026", notes_tags="artisans"),
        make_reservation(guest_name="Leo Cyrus", source_date="Jul 10, 2026", notes_tags="artisans"),
    ]
    results = match_reservations([guest], unrelated_reservations)
    for result in results:
        assert result.guest is None
        assert "no_match_found" in result.flags


def test_dotted_initial_first_name_still_matches():
    """Regression test for a real sample-data case (Guest A: dotted-initial
    first name on the guest list, undotted on Yelp): a guest-list first
    name with dotted initials ('C.J.') must still match the same person's
    Yelp row without periods ('CJ') -- the period difference alone must
    not push the first-name-agreement score below threshold and reject a
    genuine match."""
    guest = make_guest(
        confirmation_number="R-7", guest_name="Eastman, C.J.",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    reservation = make_reservation(
        guest_name="CJ Eastman", source_date="Jul 11, 2026", notes_tags="artisans",
    )
    results = match_reservations([guest], [reservation])
    assert results[0].guest is guest


def test_middle_initial_does_not_block_typo_match():
    """Regression test for a real sample-data case (Guest B: guest-list
    name has a trailing middle initial, Yelp row has a first-name typo): a
    guest-list first name with a trailing middle initial ('Annabelle K')
    must still match a typo'd Yelp name ('Anabelle') on the strength of
    the actual first name alone -- the middle initial must not be folded
    into the first-name comparison and drag a genuine typo match below
    threshold."""
    guest = make_guest(
        confirmation_number="R-8", guest_name="Garfield, Annabelle K",
        arrival_date="07/10/2026", departure_date="07/13/2026",
    )
    reservation = make_reservation(
        guest_name="Garfeld, Anabelle", source_date="Jul 11, 2026", notes_tags="artisans",
    )
    results = match_reservations([guest], [reservation])
    assert results[0].guest is guest


# --- find_room_groups ---------------------------------------------------


def test_find_room_groups_excludes_single_room_guests():
    guest = make_guest(confirmation_number="F-1", guest_name="Clarkson, Olivia")
    assert find_room_groups([guest]) == []


def test_find_room_groups_same_surname_different_first_name():
    guests = [
        make_guest(confirmation_number="G-1", guest_name="Bieber, Daniel",
                   room_name="OWLS", arrival_date="07/10/2026", departure_date="07/12/2026"),
        make_guest(confirmation_number="G-2", guest_name="Bieber, Sophia",
                   room_name="MOSS", arrival_date="07/10/2026", departure_date="07/12/2026"),
    ]
    groups = find_room_groups(guests)
    assert len(groups) == 1
    assert groups[0].matched_by == "same_surname"
    assert {r.confirmation_number for r in groups[0].records} == {"G-1", "G-2"}


def test_find_room_groups_same_surname_requires_same_dates():
    guests = [
        make_guest(confirmation_number="H-1", guest_name="Cyrus, Amy",
                   arrival_date="07/10/2026", departure_date="07/12/2026"),
        make_guest(confirmation_number="H-2", guest_name="Cyrus, Ben",
                   arrival_date="07/15/2026", departure_date="07/17/2026"),
    ]
    assert find_room_groups(guests) == []


def test_find_room_groups_exact_name_three_rooms_one_group():
    guests = [
        make_guest(confirmation_number=f"I-{i}", guest_name="Jackson, John", room_name=room)
        for i, room in enumerate(["TAMAR", "STREG", "HEARTH"], start=1)
    ]
    groups = find_room_groups(guests)
    assert len(groups) == 1
    assert groups[0].matched_by == "exact_name"
    assert len(groups[0].records) == 3


# --- detect_room_moves ----------------------------------------------------


def test_room_move_detected_when_room_and_type_both_change():
    earlier = make_guest(
        confirmation_number="J-1", guest_name="Depp, Emma",
        room_name="MOSS", room_type="1KF",
        arrival_date="07/10/2026", departure_date="07/12/2026",
    )
    later = make_guest(
        confirmation_number="J-2", guest_name="Depp, Emma",
        room_name="BIRCH", room_type="SBKP",
        arrival_date="07/12/2026", departure_date="07/14/2026",
    )
    moves = detect_room_moves([earlier, later])
    assert len(moves) == 1
    assert moves[0].earlier.room_name == "MOSS"
    assert moves[0].later.room_name == "BIRCH"


def test_multi_room_family_booking_not_a_false_move():
    """Same dates, different rooms, same guest name -- not a room move
    since dates don't chain sequentially."""
    guests = [
        make_guest(confirmation_number=f"K-{i}", guest_name="Hanks, Laura", room_name=room,
                   arrival_date="07/10/2026", departure_date="07/13/2026")
        for i, room in enumerate(["TAHAW", "AMPER", "MTJO"], start=1)
    ]
    assert detect_room_moves(guests) == []


def test_room_name_change_alone_is_not_a_move():
    """Room type stays the same -- a same-category reassignment, not a
    real move."""
    earlier = make_guest(
        confirmation_number="L-1", guest_name="Swift, Michael",
        room_name="MOSS", room_type="1KF",
        arrival_date="07/10/2026", departure_date="07/12/2026",
    )
    later = make_guest(
        confirmation_number="L-2", guest_name="Swift, Michael",
        room_name="BIRCH", room_type="1KF",
        arrival_date="07/12/2026", departure_date="07/14/2026",
    )
    assert detect_room_moves([earlier, later]) == []


# --- cross_check_notes ------------------------------------------------


def test_notes_yelp_mismatch_detected():
    """Note says Artisans, but the guest's actual Yelp reservation that
    day is at Maggie's -- a likely staff note-entry error, must surface
    as 'mismatch'."""
    guest = make_guest(
        confirmation_number="M-1", guest_name="Sheeran, Steve",
        arrival_date="07/10/2026", departure_date="07/12/2026",
        comments_notes="artisans on 7/10 @ 6pm",
    )
    reservation = make_reservation(
        guest_name="Steve Sheeran", source_date="Jul 10, 2026",
        restaurant="Maggie's", notes_tags="maggie's",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    assert any(c.status == "mismatch" for c in checks)


def test_reservation_without_note_surfaces():
    """A guest can have a real matched Yelp reservation that isn't
    mentioned in any note field -- staff notes being incomplete is
    exactly the kind of gap this tool should catch."""
    guest = make_guest(confirmation_number="N-1", guest_name="Clarkson, Olivia")
    reservation = make_reservation(guest_name="Olivia Clarkson", source_date="Jul 10, 2026")
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    assert any(c.status == "reservation_without_note" for c in checks)


def test_matched_note_and_reservation_line_up():
    guest = make_guest(
        confirmation_number="O-1", guest_name="Bieber, Daniel",
        arrival_date="07/10/2026", departure_date="07/12/2026",
        comments_notes="Artisans 7/10 @ 7PM",
    )
    reservation = make_reservation(
        guest_name="Daniel Bieber", source_date="Jul 10, 2026", restaurant="Artisans",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    assert any(c.status == "matched" for c in checks)


def test_note_time_disagrees_with_yelp_time_flagged_time_mismatch():
    """Same guest, same restaurant, same date -- but the note says 7PM and
    the actual Yelp reservation is at 6:30PM. Restaurant+date agreeing
    isn't enough to call this 'matched'; the time disagreement itself
    must be flagged so staff know to double check which time is right."""
    guest = make_guest(
        confirmation_number="O2-1", guest_name="Smith, John",
        arrival_date="07/20/2026", departure_date="07/23/2026",
        comments_notes="Artisans 7/21 @ 7PM",
    )
    reservation = make_reservation(
        guest_name="John Smith", source_date="Jul 21, 2026", time="6:30", restaurant="Artisans",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    time_mismatch_checks = [c for c in checks if c.status == "time_mismatch"]
    assert len(time_mismatch_checks) == 1
    assert "7PM" in time_mismatch_checks[0].detail
    assert "6:30" in time_mismatch_checks[0].detail
    assert not any(c.status == "matched" for c in checks)


def test_note_time_matches_yelp_time_still_matched():
    """Sanity check for the fix above: when the note's time and Yelp's
    time actually agree, it must still report 'matched', not regress into
    a false time_mismatch."""
    guest = make_guest(
        confirmation_number="O3-1", guest_name="Smith, John",
        arrival_date="07/20/2026", departure_date="07/23/2026",
        comments_notes="Artisans 7/21 @ 7PM",
    )
    reservation = make_reservation(
        guest_name="John Smith", source_date="Jul 21, 2026", time="7:00", restaurant="Artisans",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    assert any(c.status == "matched" for c in checks)
    assert not any(c.status == "time_mismatch" for c in checks)


def test_note_with_no_time_still_matches_without_time_check():
    """A note that mentions the restaurant/date but no time at all (no
    AM/PM marker -- see parsing/notes/dates.py's TIME_RE) has nothing to compare
    against Yelp's time, so it must stay a clean 'matched', not be
    penalized for a comparison that isn't possible."""
    guest = make_guest(
        confirmation_number="O4-1", guest_name="Smith, John",
        arrival_date="07/20/2026", departure_date="07/23/2026",
        comments_notes="Artisans 7/21",
    )
    reservation = make_reservation(
        guest_name="John Smith", source_date="Jul 21, 2026", time="6:30", restaurant="Artisans",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    assert any(c.status == "matched" for c in checks)
    assert not any(c.status == "time_mismatch" for c in checks)


def test_ambiguous_weekday_resolved_via_matched_yelp_reservation():
    """A long enough stay makes a weekday-only note ambiguous by date
    alone; if exactly one candidate date has a matching Yelp reservation,
    that resolves it instead of leaving it permanently unresolved."""
    guest = make_guest(
        confirmation_number="P-1", guest_name="Cyrus, Sophia",
        arrival_date="06/23/2026", departure_date="07/05/2026",
        reservation_notes="FRIDAY ARTISANS 7PM",
    )
    reservation = make_reservation(
        guest_name="Sophia Cyrus", source_date="Jun 26, 2026", restaurant="Artisans",
    )
    match_results = match_reservations([guest], [reservation])
    checks = cross_check_notes([guest], match_results)
    matched = [c for c in checks if c.status == "matched"]
    assert len(matched) == 1
    assert matched[0].mention.resolved_date == date(2026, 6, 26)


def test_no_reservations_do_not_crash_cross_check():
    guest = make_guest(confirmation_number="Q-1", guest_name="Jackson, John")
    checks = cross_check_notes([guest], [])
    assert isinstance(checks, list)
