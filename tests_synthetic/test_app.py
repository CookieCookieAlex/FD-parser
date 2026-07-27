"""Regression tests for fd_reader.app's pure logic, using the synthetic
PDFs from tests_synthetic/pdf_writer.py instead of the real guest-notes/
folder. Does not drive the browser (see run/playwright-based manual
verification for that); this just checks the functions app.py calls
behave correctly in isolation.
"""
import glob
import os
import tempfile

from fd_reader.app_ui import _load_from_uploads, _mtime_fingerprint, _run_pipeline, block_worst_color
from fd_reader.report import BLUE, GREEN, RED, YELLOW

from tests_synthetic.pdf_writer import build_synthetic_arrivals_pdf, build_synthetic_yelp_pdfs

ARRIVALS_PDF = os.path.join(os.path.dirname(__file__), "_generated_app_arrivals.pdf")
YELP_DIR = os.path.join(os.path.dirname(__file__), "_generated_app_yelp_days")


def _run_pipeline_for_paths(guest_paths, yelp_paths):
    return _run_pipeline(
        guest_paths, yelp_paths, _mtime_fingerprint(guest_paths), _mtime_fingerprint(yelp_paths)
    )


def setup_module(module):
    build_synthetic_arrivals_pdf(ARRIVALS_PDF)
    os.makedirs(YELP_DIR, exist_ok=True)
    build_synthetic_yelp_pdfs(YELP_DIR)


def teardown_module(module):
    if os.path.exists(ARRIVALS_PDF):
        os.remove(ARRIVALS_PDF)
    if os.path.isdir(YELP_DIR):
        for name in os.listdir(YELP_DIR):
            os.remove(os.path.join(YELP_DIR, name))
        os.rmdir(YELP_DIR)


def _yelp_paths():
    return tuple(sorted(os.path.join(YELP_DIR, name) for name in os.listdir(YELP_DIR)))


def test_run_pipeline_produces_expected_counts():
    """Real end-to-end shape: 1 arrivals PDF (15 guests) + 8 single-day
    Yelp PDFs (one reservation each) -- the same file mix a real 7/8-day
    folder would have."""
    blocks, room_move_count, group_booking_count = _run_pipeline_for_paths((ARRIVALS_PDF,), _yelp_paths())
    assert len(blocks) == 15
    # Bieber, Daniel: MOSS -> BIRCH is the one synthetic room move.
    assert room_move_count == 1
    # Hanks (3-room exact-name) + Depp (2-room same-surname) = 2 groups.
    assert group_booking_count == 2


def test_run_pipeline_matches_reservation_to_guest():
    blocks, _, _ = _run_pipeline_for_paths((ARRIVALS_PDF,), _yelp_paths())
    jackson_block = next(b for b in blocks if "Jackson" in b.guest.guest_name)
    assert any(line.reservation is not None for line in jackson_block.lines)


def test_run_pipeline_outside_guest_never_matched_to_a_block():
    """bill jennings' outside-guest reservation must not attach to any
    guest's block."""
    blocks, _, _ = _run_pipeline_for_paths((ARRIVALS_PDF,), _yelp_paths())
    for block in blocks:
        for line in block.lines:
            if line.reservation is not None:
                assert line.reservation.guest_name != "bill jennings"


def test_block_worst_color_picks_most_severe():
    from fd_reader.report import GuestBlock, ReservationLine

    class FakeGuest:
        guest_name = "Test"

    block = GuestBlock(
        guest=FakeGuest(),
        lines=[
            ReservationLine(color=GREEN, note="fine"),
            ReservationLine(color=YELLOW, note="hmm"),
        ],
    )
    assert block_worst_color(block) == YELLOW

    block.lines.append(ReservationLine(color=RED, note="bad"))
    assert block_worst_color(block) == RED


def test_block_worst_color_all_green_stays_green():
    from fd_reader.report import GuestBlock, ReservationLine

    class FakeGuest:
        guest_name = "Test"

    block = GuestBlock(guest=FakeGuest(), lines=[ReservationLine(color=GREEN, note="fine")])
    assert block_worst_color(block) == GREEN


def test_block_worst_color_blue_only():
    from fd_reader.report import GuestBlock, ReservationLine

    class FakeGuest:
        guest_name = "Test"

    block = GuestBlock(guest=FakeGuest(), lines=[ReservationLine(color=BLUE, note="none")])
    assert block_worst_color(block) == BLUE


def test_mtime_fingerprint_changes_when_file_is_resaved():
    """Regression test for a stale-cache risk: _run_pipeline is
    @st.cache_data-cached by its arguments, and in "Folder path" mode the
    path stays constant across reloads -- so re-saving an edited PDF to
    the same path used to be invisible to the cache, silently serving the
    old parsed results. _mtime_fingerprint must change whenever a file's
    mtime changes, so it's included in the cache key."""
    before = _mtime_fingerprint((ARRIVALS_PDF,))

    with open(ARRIVALS_PDF, "ab") as f:
        f.write(b" ")
    new_mtime = os.path.getmtime(ARRIVALS_PDF) + 1
    os.utime(ARRIVALS_PDF, (new_mtime, new_mtime))

    after = _mtime_fingerprint((ARRIVALS_PDF,))
    assert before != after


class _FakeUploadedFile:
    """Minimal stand-in for Streamlit's UploadedFile -- _load_from_uploads
    only ever calls .name and .getbuffer() on it."""

    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getbuffer(self):
        return self._content


def _leaked_upload_dirs():
    return glob.glob(os.path.join(tempfile.gettempdir(), "fd_reader_upload_*"))


def test_load_from_uploads_cleans_up_temp_dir_on_failure():
    """Regression test: _load_from_uploads used to leak a fresh temp
    directory (with real uploaded PDF copies inside) on every call, never
    deleting it -- including on the "couldn't find a valid PDF" failure
    path. It must clean up regardless of outcome."""
    before = set(_leaked_upload_dirs())
    fake_files = [_FakeUploadedFile("not_a_real_pdf.pdf", b"garbage, not a real PDF")]

    result = _load_from_uploads(fake_files)

    assert result is None
    after = set(_leaked_upload_dirs())
    assert after == before, f"leaked temp dir(s): {after - before}"


def test_load_from_uploads_cleans_up_temp_dir_on_success():
    before = set(_leaked_upload_dirs())
    with open(ARRIVALS_PDF, "rb") as f:
        arrivals_bytes = f.read()
    fake_files = [_FakeUploadedFile("Arrivals with Details.pdf", arrivals_bytes)]
    for path in _yelp_paths():
        with open(path, "rb") as f:
            fake_files.append(_FakeUploadedFile(os.path.basename(path), f.read()))

    result = _load_from_uploads(fake_files)

    assert result is not None
    after = set(_leaked_upload_dirs())
    assert after == before, f"leaked temp dir(s): {after - before}"
