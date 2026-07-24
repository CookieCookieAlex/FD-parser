"""Regression tests for fd_reader.parsing.guests using entirely synthetic
data -- no real guest-notes/ PDFs involved. Covers the same structural
cases documented in CLAUDE.md (blank room name, repeated guest name across
multiple rooms, cross-page note continuation, multi-entry Comments/Notes,
inline lifetime fields) but with made-up guests (see
tests_synthetic/fixtures.py).

Two layers are tested:
  - Row/Word-level: RecordBuilder/match_label/is_record_anchor directly,
    with hand-built Row/Word objects -- fast, no PDF rendering.
  - End-to-end: a tiny reportlab-generated PDF run through the real
    parse_guest_pdf(path), which cannot accept pre-built Row objects since
    it opens the file itself.
"""
import os

from fd_reader.parsing.guests import parse_guest_pdf
from fd_reader.parsing.guests.record_builder import RecordBuilder, match_label
from fd_reader.parsing.guests.rows import is_boilerplate, is_record_anchor, is_stay_date_row

from tests_synthetic.fixtures import guest_row, guest_word, make_anchor_row, make_detail_row, make_label_row
from tests_synthetic.pdf_writer import build_synthetic_arrivals_pdf

SYNTHETIC_PDF = os.path.join(os.path.dirname(__file__), "_generated_synthetic_arrivals.pdf")


def setup_module(module):
    build_synthetic_arrivals_pdf(SYNTHETIC_PDF)


def teardown_module(module):
    if os.path.exists(SYNTHETIC_PDF):
        os.remove(SYNTHETIC_PDF)


# --- Row/Word-level tests -------------------------------------------------


def test_is_record_anchor_detects_status_and_arrival_date():
    row = make_anchor_row("PINEVW", "Jackson, John")
    assert is_record_anchor(row) == ("Reserved", "07/10/2026")


def test_is_record_anchor_none_without_status():
    row = guest_row([guest_word("07/10/2026", 350)])
    assert is_record_anchor(row) is None


def test_blank_room_name_flagged_missing_room_name():
    """Room type set, room name blank -- the 'needs room assignment fix'
    case from CLAUDE.md, reproduced with a fake guest."""
    anchor = make_anchor_row("", "Depp, Emma")
    status, arrival = is_record_anchor(anchor)
    builder = RecordBuilder(status, arrival, source_page=1)
    builder.consume_anchor_row(anchor)
    builder.consume_detail_row(make_detail_row("LL1KF", "SYN-2001-1", "07/14/2026"))
    record = builder.finalize()

    assert record.room_name == ""
    assert record.room_type == "LL1KF"
    assert "missing_room_name" in record.flags


def test_guests_count_and_share_parsed_as_separate_ints():
    anchor = make_anchor_row("BUCK", "Sheeran, Steve", guests_count="2", guests_share="2")
    status, arrival = is_record_anchor(anchor)
    builder = RecordBuilder(status, arrival, source_page=1)
    builder.consume_anchor_row(anchor)
    assert builder.guests_count == 2
    assert builder.guests_share == 2


def test_rate_plan_parsed_from_anchor_row():
    anchor = make_anchor_row("MTVIEW", "Hanks, Laura", rate_plan="VIRTUO")
    status, arrival = is_record_anchor(anchor)
    builder = RecordBuilder(status, arrival, source_page=1)
    builder.consume_anchor_row(anchor)
    assert builder.rate_plan == "VIRTUO"


def test_unknown_status_flagged_not_dropped():
    anchor = make_anchor_row("PINEVW", "Swift, Michael", status="CheckedIn")
    status, arrival = is_record_anchor(anchor)
    assert status == "CheckedIn"
    builder = RecordBuilder(status, arrival, source_page=1)
    builder.consume_anchor_row(anchor)
    record = builder.finalize()
    assert "unknown_status:CheckedIn" in record.flags


def test_match_label_guest_notes():
    row = make_label_row("Guest Notes:", "No allergies noted.", top=124)
    result = match_label(row)
    assert result == ("guest_notes", "No allergies noted.")


def test_match_label_comments_notes_multiword_label():
    row = guest_row(
        [
            guest_word("Comments", 40, 174), guest_word("/", 90, 174), guest_word("Notes:", 100, 174),
            guest_word("Artisans", 165, 174), guest_word("7/11", 210, 174),
        ],
        top=174,
    )
    result = match_label(row)
    assert result == ("comments_notes", "Artisans 7/11")


def test_comments_notes_multiple_entries_blank_line_separated():
    """Comments/Notes is a running log -- multiple append_field_text calls
    must join with a blank line, not run together."""
    builder = RecordBuilder("Reserved", "07/10/2026", source_page=1)
    builder.append_field_text("comments_notes", "Maggie's 7/10 @ 7PM")
    builder.append_field_text("comments_notes", "Artisans 7/12 @ 6:30PM")
    record = builder.finalize()
    entries = record.comments_notes.split("\n\n")
    assert entries == ["Maggie's 7/10 @ 7PM", "Artisans 7/12 @ 6:30PM"]


def test_cross_page_note_continuation_attaches_to_active_field():
    """A note continuation line (no label of its own, text only right of
    the label boundary) must append to the currently-active field -- this
    is how a note surviving a page break attaches to the right guest."""
    builder = RecordBuilder("Reserved", "07/10/2026", source_page=1)
    label_row = make_label_row("Guest Notes:", "Allergic to shellfish,", top=124)
    field, value = match_label(label_row)
    builder.consume_label_row(field, value)
    assert builder.active_field == "guest_notes"

    continuation_row = guest_row([guest_word("no", 165, 300), guest_word("nuts.", 185, 300)], top=300)
    left_text = continuation_row.text_in_range(x0=None, x1=160.0).strip()
    assert left_text == ""  # confirms this row would be treated as a continuation
    builder.append_field_text(builder.active_field, continuation_row.text_in_range(x0=160.0).strip())

    record = builder.finalize()
    assert record.guest_notes == "Allergic to shellfish, no nuts."


def test_last_stay_property_and_lifetime_fields_split_correctly():
    """One inline row packs 4 sub-fields -- must split, not stay one blob."""
    row = make_label_row(
        "Last Stay Property:",
        "0317 Lifetime Revenue: $2,218.77 Lifetime Stays: 1 Lifetime Nights: 2",
        top=200,
    )
    field, value = match_label(row)
    assert field == "last_stay_property"
    builder = RecordBuilder("Reserved", "07/10/2026", source_page=1)
    builder.consume_label_row(field, value)
    record = builder.finalize()
    assert record.last_stay_property == "0317"
    assert record.lifetime_revenue == "$2,218.77"
    assert record.lifetime_stays == "1"
    assert record.lifetime_nights == "2"


def test_is_stay_date_row_skipped():
    row = guest_row(
        [guest_word("Stay", 20, 130), guest_word("Date", 55, 130), guest_word("(Days)", 90, 130)],
        top=130,
    )
    assert is_stay_date_row(row)


def test_is_boilerplate_header_rows():
    row = guest_row([guest_word("Arrivals", 20, 10), guest_word("with", 70, 10), guest_word("Details", 100, 10)], top=10)
    assert is_boilerplate(row)


# --- End-to-end synthetic-PDF tests ----------------------------------------


def test_synthetic_pdf_parses_all_fourteen_guests():
    records = parse_guest_pdf(SYNTHETIC_PDF)
    assert len(records) == 14
    names = {r.guest_name for r in records}
    assert names == {
        "Jackson, John", "Sheeran, Steve", "Depp, Emma", "Depp, Olivia",
        "Hanks, Laura", "Swift, Michael", "Bieber, Daniel",
        "Clarkson, Olivia", "Cyrus, Sophia", "Turner, Grace", "Wilson, Henry",
    }


def test_synthetic_pdf_no_unrecognized_rows_or_unknown_status():
    records = parse_guest_pdf(SYNTHETIC_PDF)
    for r in records:
        assert not any(f.startswith("unrecognized_row") for f in r.flags)
        assert not any(f.startswith("unknown_status") for f in r.flags)


def test_synthetic_pdf_jackson_clean_match_fields():
    records = {r.confirmation_number: r for r in parse_guest_pdf(SYNTHETIC_PDF)}
    jackson = records["SYN-1001-1"]
    assert jackson.guest_name == "Jackson, John"
    assert jackson.room_name == "PINE"
    assert jackson.room_type == "SPKP"
    assert jackson.arrival_date == "07/10/2026"
    assert jackson.departure_date == "07/13/2026"
    assert jackson.guests_count == 2
    assert jackson.rate_plan == "LEIS"
    assert jackson.comments_notes == "Artisans 7/10 @ 7PM"


def test_synthetic_pdf_sheeran_blank_room_name_flagged():
    """Room type set, room name blank -- the 'needs room assignment fix'
    case from CLAUDE.md, reproduced end-to-end through a real PDF."""
    records = {r.confirmation_number: r for r in parse_guest_pdf(SYNTHETIC_PDF)}
    sheeran = records["SYN-1002-1"]
    assert sheeran.room_name == ""
    assert sheeran.room_type == "LL1KF"
    assert "missing_room_name" in sheeran.flags


def test_synthetic_pdf_hanks_three_rooms_same_guest():
    records = parse_guest_pdf(SYNTHETIC_PDF)
    hanks = [r for r in records if r.guest_name == "Hanks, Laura"]
    assert len(hanks) == 3
    assert {r.room_name for r in hanks} == {"TAHAW", "AMPER", "MTJO"}
    assert len({r.confirmation_number for r in hanks}) == 3


def test_synthetic_pdf_swift_virtuoso_and_breakfast_typo_in_notes():
    records = {r.confirmation_number: r for r in parse_guest_pdf(SYNTHETIC_PDF)}
    swift = records["SYN-1008-1"]
    assert "VIRTUOSO" in swift.reservation_notes
    assert "BREAKFAST INCLLUDED" in swift.reservation_notes


def test_synthetic_pdf_bieber_two_records_for_room_move():
    records = parse_guest_pdf(SYNTHETIC_PDF)
    bieber = [r for r in records if r.guest_name == "Bieber, Daniel"]
    assert len(bieber) == 2
    earlier = next(r for r in bieber if r.room_name == "MOSS")
    later = next(r for r in bieber if r.room_name == "BIRCH")
    assert earlier.departure_date == later.arrival_date == "07/12/2026"


def test_synthetic_pdf_clarkson_weekday_only_note():
    records = {r.confirmation_number: r for r in parse_guest_pdf(SYNTHETIC_PDF)}
    clarkson = records["SYN-1011-1"]
    assert clarkson.reservation_notes == "FRIDAY ARTISANS 7PM"


def test_synthetic_pdf_cyrus_multi_entry_comments_notes_across_page_break():
    """Comments/Notes is a running log -- the second entry lands on a new
    page (page break), continuation must attach to Cyrus, not get dropped
    or merged into one run-on string."""
    records = {r.confirmation_number: r for r in parse_guest_pdf(SYNTHETIC_PDF)}
    cyrus = records["SYN-1012-1"]
    entries = cyrus.comments_notes.split("\n\n")
    assert entries[0] == "Maggie's 7/11 @ 6:30PM"
    assert "PET AMENITIES" in entries[-1]
