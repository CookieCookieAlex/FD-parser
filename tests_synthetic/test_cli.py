"""Regression tests for fd_reader.cli's folder auto-detection using
synthetic PDFs (see tests_synthetic/pdf_writer.py) instead of the real
guest-notes/ folder: 1 arrivals PDF (12 fake guests) + 8 single-day Yelp
PDFs, matching the real "one arrivals report + one Yelp file per day"
workflow, with deliberately generic/mixed Yelp filenames (never restaurant-
named) to prove classification/matching work from file content, not names.
"""
import os

import openpyxl
import pytest

from fd_reader.cli import _classify_pdf, _discover_pdfs, main

from tests_synthetic.pdf_writer import build_synthetic_arrivals_pdf, build_synthetic_yelp_pdfs


@pytest.fixture()
def synthetic_folder(tmp_path):
    arrivals_path = tmp_path / "synthetic_arrivals.pdf"
    build_synthetic_arrivals_pdf(str(arrivals_path))
    build_synthetic_yelp_pdfs(str(tmp_path))
    return tmp_path


def test_classify_arrivals_pdf(synthetic_folder):
    path = synthetic_folder / "synthetic_arrivals.pdf"
    assert _classify_pdf(str(path)) == "guests"


def test_classify_yelp_pdf(synthetic_folder):
    path = synthetic_folder / "Yelp for Business.pdf"
    assert _classify_pdf(str(path)) == "yelp"


def test_classify_yelp_pdf_with_artisans_titled_filename():
    """Confirmed real per CLAUDE.md: a file titled 'Artisans at the Lake
    Placid Lodge' still classifies as 'yelp' by content, regardless of its
    restaurant-sounding filename."""
    import tempfile

    from tests_synthetic.pdf_writer import _write_single_day_yelp_pdf

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "Artisans at the Lake Placid Lodge _ Yelp for Business.pdf")
        _write_single_day_yelp_pdf(path, "Fri, Jul 10, 2026", [("7:00", 2, "Test Guest", "artisans")])
        assert _classify_pdf(path) == "yelp"


def test_discover_pdfs_finds_all_nine_files(synthetic_folder):
    """1 arrivals PDF + 8 single-day Yelp PDFs -- must find and classify
    all 9, not stop at the first of each kind."""
    guest_files, yelp_files = _discover_pdfs(str(synthetic_folder))
    assert len(guest_files) == 1
    assert len(yelp_files) == 8


def test_discover_pdfs_ignores_unrelated_pdf(synthetic_folder, capsys):
    # A PDF with neither marker text should be skipped, not misclassified.
    from reportlab.pdfgen import canvas

    other_path = synthetic_folder / "unrelated.pdf"
    c = canvas.Canvas(str(other_path))
    c.drawString(50, 700, "Just some other document")
    c.save()

    guest_files, yelp_files = _discover_pdfs(str(synthetic_folder))
    assert len(guest_files) == 1
    assert len(yelp_files) == 8
    captured = capsys.readouterr()
    assert "Skipped 1 PDF" in captured.err


def test_main_folder_mode_combines_arrivals_and_all_yelp_days(synthetic_folder, capsys):
    """Both the arrivals PDF's guests and all 8 Yelp days' reservations
    must be combined into one report, not just the first file of each
    kind."""
    out = synthetic_folder / "report.xlsx"
    exit_code = main(["--folder", str(synthetic_folder), "--out", str(out)])
    assert exit_code == 0
    assert out.exists()

    captured = capsys.readouterr()
    assert "1 arrivals PDF(s)" in captured.out
    assert "8 Yelp PDF(s)" in captured.out
    assert "15 guests" in captured.out
    assert "8 reservations" in captured.out
    assert "1 room move" in captured.out
    assert "2 group booking" in captured.out

    workbook = openpyxl.load_workbook(str(out))
    assert workbook.active.max_row > 12


def test_folder_and_explicit_flags_conflict(synthetic_folder):
    with pytest.raises(SystemExit):
        main([
            "--folder", str(synthetic_folder),
            "--guests", str(synthetic_folder / "synthetic_arrivals.pdf"),
            "--out", str(synthetic_folder / "unused.xlsx"),
        ])


def test_empty_folder_errors_cleanly(tmp_path):
    with pytest.raises(SystemExit):
        main(["--folder", str(tmp_path), "--out", str(tmp_path / "out.xlsx")])
