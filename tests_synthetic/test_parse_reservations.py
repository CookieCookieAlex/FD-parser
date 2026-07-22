"""Regression tests for fd_reader.parsing.reservations using entirely
synthetic data -- no real guest-notes/ Yelp PDFs involved. Covers the same
structural cases documented in CLAUDE.md (restaurant identity parsed from
Notes & Tags rather than filename, room-code shorthand, internal shorthand
tokens (GH/hg/...), outside-guest detection) but with made-up guests (see
tests_synthetic/fixtures.py). The 8-file split (one reservation per file)
mirrors the real workflow: Yelp for Business only exports a single day per
PDF, and filenames are deliberately generic/mixed (not restaurant-named) to
prove restaurant identity is read from file CONTENT, never the filename.
"""
import os

from fd_reader.parsing.reservations import (
    _derive_restaurant,
    _extract_room_code_hint,
    _is_boilerplate,
    _is_outside_guest,
    _is_reservation_start_row,
    _parse_party_size,
    parse_reservation_pdf,
)

from tests_synthetic.fixtures import (
    make_notes_continuation_row,
    make_phone_row,
    make_reservation_start_row,
    yelp_row,
    yelp_word,
)
from tests_synthetic.pdf_writer import YELP_DAYS, build_synthetic_yelp_pdf, build_synthetic_yelp_pdfs

SYNTHETIC_PDF = os.path.join(os.path.dirname(__file__), "_generated_synthetic_yelp.pdf")
SYNTHETIC_DIR = os.path.join(os.path.dirname(__file__), "_generated_synthetic_yelp_days")


def setup_module(module):
    build_synthetic_yelp_pdf(SYNTHETIC_PDF, source_date_label="Fri, Jul 10, 2026")
    os.makedirs(SYNTHETIC_DIR, exist_ok=True)
    build_synthetic_yelp_pdfs(SYNTHETIC_DIR)


def teardown_module(module):
    if os.path.exists(SYNTHETIC_PDF):
        os.remove(SYNTHETIC_PDF)
    if os.path.isdir(SYNTHETIC_DIR):
        for name in os.listdir(SYNTHETIC_DIR):
            os.remove(os.path.join(SYNTHETIC_DIR, name))
        os.rmdir(SYNTHETIC_DIR)


def _parse_day(filename: str):
    return parse_reservation_pdf(os.path.join(SYNTHETIC_DIR, filename))


# --- Row/Word-level tests -------------------------------------------------


def test_is_reservation_start_row_detects_time():
    row = make_reservation_start_row("7:00", "2", "John Jackson")
    assert _is_reservation_start_row(row)


def test_is_reservation_start_row_false_for_note_only_row():
    row = make_notes_continuation_row("still artisans PINEVW", top=110)
    assert not _is_reservation_start_row(row)


def test_parse_party_size_reads_digit_in_column():
    row = make_reservation_start_row("6:30", "4", "Steve Sheeran")
    assert _parse_party_size(row) == 4


def test_restaurant_derived_from_notes_not_filename():
    """A row's restaurant identity always comes from Notes & Tags text,
    per CLAUDE.md -- confirmed here independent of any filename."""
    assert _derive_restaurant("artisans PINEVW no allergies") == "Artisans"
    assert _derive_restaurant("maggie's - BUCK") == "Maggie's"
    assert _derive_restaurant("no restaurant keyword here") is None


def test_outside_guest_detected_from_notes():
    assert _is_outside_guest("artisans off property no allergies")
    assert not _is_outside_guest("artisans PINEVW")


def test_room_code_hint_strips_restaurant_and_shorthand_tokens():
    """The restaurant keyword regex matches 'artisan' (not 'artisans'), so
    a trailing 's' survives -- this matches real Notes & Tags hints like
    "'s AUSABL" seen in CLAUDE.md, which fd_reader.rooms.aliases already
    strips on the resolution side."""
    hint = _extract_room_code_hint("artisans PINEVW GH")
    assert hint == "s PINEVW"


def test_boilerplate_footer_row_detected():
    row = yelp_row([yelp_word("Copyright", 60, 700), yelp_word("Yelp", 120, 700), yelp_word("Inc.", 150, 700)], top=700)
    assert _is_boilerplate(row)


def test_boilerplate_page_title_row_excluded_by_low_top():
    """Page-title timestamp looks exactly like a real Time-column value --
    must be excluded by its low `top`, not by text content."""
    row = yelp_row([yelp_word("12:17", 40, 20), yelp_word("PM", 70, 20)], top=20)
    assert _is_boilerplate(row)


def test_phone_row_regex_matches_parenthesized_area_code():
    row = make_phone_row("(518)", "524-3417", top=112)
    phone_word = row.words[0]
    from fd_reader.parsing.reservations import PHONE_RE

    assert PHONE_RE.match(phone_word.text)


# --- End-to-end synthetic-PDF tests (single file) --------------------------


def test_synthetic_pdf_parses_one_reservation():
    records = parse_reservation_pdf(SYNTHETIC_PDF)
    assert len(records) == 1
    assert records[0].guest_name == "John Jackson"


def test_synthetic_pdf_source_date_from_filter_bar():
    records = parse_reservation_pdf(SYNTHETIC_PDF)
    assert all(r.source_date == "Jul 10, 2026" for r in records)


def test_synthetic_pdf_no_boilerplate_leak_into_notes():
    records = parse_reservation_pdf(SYNTHETIC_PDF)
    for r in records:
        assert "Copyright" not in r.notes_tags
        assert "Yelp for Business" not in r.notes_tags


# --- End-to-end: 8 single-day PDFs, one reservation per file ---------------


def test_eight_day_files_all_have_exactly_one_reservation_each():
    """Real Yelp exports are one day per PDF -- confirm all 8 fixture
    files round-trip through parse_reservation_pdf() individually."""
    for filename, _, _ in YELP_DAYS:
        records = _parse_day(filename)
        assert len(records) == 1


def test_restaurant_titled_file_actually_contains_a_maggies_row():
    """Confirmed real per CLAUDE.md: a file titled 'Artisans at the Lake
    Placid Lodge' can contain a Maggie's reservation -- restaurant identity
    must come from Notes & Tags, never the filename. Day 5's file is
    Artisans-titled but Daniel Bieber's row is a Maggie's reservation."""
    records = _parse_day("Yelp for Business3.pdf")
    assert records[0].restaurant == "Maggie's"
    assert records[0].guest_name == "Daniel Bieber"


def test_room_code_hint_with_comma_punctuation():
    """'artisans, STLWTR' -- comma-punctuated hint, per CLAUDE.md's real
    'artisans, SADDLE' example."""
    records = _parse_day("Yelp for Business2.pdf")
    assert records[0].guest_name == "Emma Depp"
    assert records[0].room_code_hint is not None
    assert "STLWTR" in records[0].room_code_hint


def test_surname_only_row_with_multi_room_hint():
    records = _parse_day("Artisans at the Lake Placid Lodge _ Yelp for Business.pdf")
    assert records[0].guest_name == "HANKS"
    assert records[0].party_size == 4


def test_outside_guest_row_has_no_room_hint():
    """'bill jennings -- artisans off property no allergies' -- no
    in-house room hint at all, per CLAUDE.md's real example shape."""
    records = _parse_day("Yelp for Business4.pdf")
    assert records[0].guest_name == "bill jennings"
    assert records[0].is_outside_guest is True


def test_punctuated_hint_and_shorthand_token_stripped():
    """'Artisans- St.regis GH' -- punctuated restaurant prefix (per
    CLAUDE.md's real 'Artisans- St.regis' -> STREG example) plus an
    internal shorthand token (GH) that must be stripped from the hint but
    not decoded (per CLAUDE.md, meaning is intentionally unknown)."""
    records = _parse_day("Artisans at the Lake Placid Lodge _ Yelp for Business4.pdf")
    record = records[0]
    assert record.guest_name == "Sophia Cyrus"
    assert record.restaurant == "Artisans"
    assert "GH" not in (record.room_code_hint or "").split()
    assert "regis" in (record.room_code_hint or "").lower()
