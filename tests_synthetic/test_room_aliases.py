"""Regression tests for fd_reader.rooms.aliases, pinned against real
Notes & Tags room-code-hint strings observed across all 14 sample Yelp
PDFs (see SESSION_HISTORY.md session 4 for how these were gathered).
"""
from fd_reader.rooms.aliases import resolve_room_code_hint


def resolved_abbrev(hint):
    room = resolve_room_code_hint(hint)
    return room.abbreviation if room else None


def test_plain_abbreviation_hints_resolve():
    assert resolved_abbrev("'s AUSABL") == "AUSABL"
    assert resolved_abbrev("'s MTMARCY") == "MTMARCY"
    assert resolved_abbrev("'s SADDLE") == "SADDLE"
    assert resolved_abbrev("'s STREG allergies 1 person shellfish strawberries") == "STREG"
    assert resolved_abbrev("s STLWTR") == "STLWTR"
    assert resolved_abbrev("s WTFACE") == "WTFACE"


def test_full_name_hints_resolve_case_insensitive():
    assert resolved_abbrev("'s lookout") == "LOOK"
    assert resolved_abbrev("s lookout lg") == "LOOK"
    assert resolved_abbrev("s Buck") == "BUCK"
    assert resolved_abbrev("s marble lg") == "MARBLE"
    assert resolved_abbrev("s tamarack lg") == "TAMAR"  # "tamarack" misspelling of Tamarac
    assert resolved_abbrev("s owls lg") == "OWLS"
    assert resolved_abbrev("S WHITEFACE TREETOP") == "WTFACE"  # first-mentioned room wins


def test_known_misspellings():
    assert resolved_abbrev("'s Kiwssa") == "KIWA"
    assert resolved_abbrev("'s Hearthide there is actually 6 people emily approved") == "HEARTH"
    assert resolved_abbrev("s ausable would like outside") == "AUSABL"


def test_two_word_room_names_via_bigram():
    assert resolved_abbrev("S St Armand") == "STARM"
    assert resolved_abbrev("s St regis") == "STREG"
    assert resolved_abbrev("S ST REGIS") == "STREG"


def test_multi_room_hint_resolves_first_mentioned():
    """A hint mentioning two rooms (family/adjacent booking) resolves to
    whichever room name appears first in the text, deterministically --
    not whichever happens to sort last."""
    assert resolved_abbrev("s Marble Ampersand CELIAC") == "MARBLE"
    assert resolved_abbrev("s 4 adults 4 kids Kiwassa/Marble VVIP comp dinner") == "KIWA"
    assert resolved_abbrev("S ST ARM SADDLE") == "STARM"


def test_non_room_terms_do_not_false_positive():
    """'Runway' and 'Wine Cellar' are real Notes & Tags text but are NOT
    any of the 32 rooms in rooms/directory.py -- must resolve to None, not
    a wrong room."""
    assert resolved_abbrev("s Runway off prop cc on file for rental fee") is None
    assert resolved_abbrev(
        "s Wine Cellar has Certificate for boat Wine Cellar Dinner"
    ) is None
    assert resolved_abbrev(
        "s Bday dinner see itinerary for notes s Runway no other guests on Runway"
    ) is None


def test_off_property_and_bare_hints_resolve_to_none():
    """No room-code signal present at all -- must not guess."""
    assert resolved_abbrev("'s off prop") is None
    assert resolved_abbrev("s") is None
    assert resolved_abbrev("S") is None
    assert resolved_abbrev("s anniversary") is None
    assert resolved_abbrev("S NO ALLERGIES") is None


def test_room_type_descriptor_does_not_false_positive_as_room_name():
    """'LAKEFRONT' is part of several room_type_desc strings, not a room
    name/abbreviation itself -- must not resolve."""
    assert resolved_abbrev("S LAKEFRONT JUNE WIFE CHRISTINE'S BIRTHDAY") is None


def test_empty_or_none_hint():
    assert resolve_room_code_hint(None) is None
    assert resolve_room_code_hint("") is None
