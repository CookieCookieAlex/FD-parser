"""Entry point: guest-arrivals PDF(s) + Yelp reservation PDF(s) -> .xlsx.

Usage (point at a folder -- auto-detects which PDFs are which, per file
content, not filename, since Yelp filenames are unreliable -- see
CLAUDE.md):
    python -m fd_reader.cli --folder guest-notes --out report.xlsx

Usage (explicit file lists, if the auto-detected split is ever wrong):
    python -m fd_reader.cli --guests arrivals.pdf [more_arrivals.pdf ...] \\
        --yelp reservation1.pdf [reservation2.pdf ...] \\
        --out report.xlsx
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import pdfplumber

from fd_reader.match import (
    cross_check_notes,
    detect_room_moves,
    find_room_groups,
    match_reservations,
)
from fd_reader.parse_guests import parse_guest_pdf
from fd_reader.parse_reservations import parse_reservation_pdf
from fd_reader.report import build_guest_blocks, write_report

# First-page text markers used to tell an arrivals-report PDF apart from a
# Yelp reservations PDF. Filename is NOT used for this -- confirmed
# unreliable for restaurant identity inside Yelp PDFs (see CLAUDE.md), and
# there's no reason to trust it any more for guest-vs-Yelp identity either.
_ARRIVALS_MARKER = "Arrivals with Details"
_YELP_MARKERS = ("Yelp for Business", "Yelp Guest Manager", "biz.yelp.com")


def _classify_pdf(path: str) -> str | None:
    """Returns 'guests', 'yelp', or None if neither marker is found on the
    first page (e.g. a non-report PDF that happens to be in the folder)."""
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None
            text = pdf.pages[0].extract_text() or ""
    except Exception:
        return None

    if _ARRIVALS_MARKER in text:
        return "guests"
    if any(marker in text for marker in _YELP_MARKERS):
        return "yelp"
    return None


def _discover_pdfs(folder: str) -> tuple[list[str], list[str]]:
    guest_paths: list[str] = []
    yelp_paths: list[str] = []
    unrecognized: list[str] = []

    for path in sorted(glob.glob(os.path.join(folder, "*.pdf"))):
        kind = _classify_pdf(path)
        if kind == "guests":
            guest_paths.append(path)
        elif kind == "yelp":
            yelp_paths.append(path)
        else:
            unrecognized.append(path)

    if unrecognized:
        print(
            f"Skipped {len(unrecognized)} PDF(s) in {folder!r} that didn't look like "
            f"an arrivals report or a Yelp export: "
            f"{', '.join(os.path.basename(p) for p in unrecognized)}",
            file=sys.stderr,
        )

    return guest_paths, yelp_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder", help="Folder containing both the arrivals PDF and all Yelp PDFs"
    )
    parser.add_argument("--guests", nargs="+", help="Guest-arrivals PDF(s) (explicit mode)")
    parser.add_argument("--yelp", nargs="+", help="Yelp reservation PDF(s) (explicit mode)")
    parser.add_argument("--out", required=True, help="Output .xlsx path")
    args = parser.parse_args(argv)

    if args.folder:
        if args.guests or args.yelp:
            parser.error("--folder cannot be combined with --guests/--yelp")
        guest_files, yelp_files = _discover_pdfs(args.folder)
    else:
        if not args.guests or not args.yelp:
            parser.error("either --folder, or both --guests and --yelp, are required")
        guest_files, yelp_files = args.guests, args.yelp

    if not guest_files:
        parser.error("no arrivals-report PDF found (looked for 'Arrivals with Details')")
    if not yelp_files:
        parser.error("no Yelp reservation PDFs found")

    guests = []
    for path in guest_files:
        guests.extend(parse_guest_pdf(path))

    reservations = []
    for path in yelp_files:
        reservations.extend(parse_reservation_pdf(path))

    match_results = match_reservations(guests, reservations)
    note_checks = cross_check_notes(guests, match_results)
    room_moves = detect_room_moves(guests)
    room_groups = find_room_groups(guests)

    blocks = build_guest_blocks(guests, match_results, note_checks, room_moves)
    write_report(
        blocks, args.out,
        room_move_count=len(room_moves),
        group_booking_count=len(room_groups),
    )

    print(
        f"{len(guest_files)} arrivals PDF(s), {len(yelp_files)} Yelp PDF(s) -> "
        f"{len(guests)} guests, {len(reservations)} reservations, "
        f"{len(room_moves)} room move(s), {len(room_groups)} group booking(s) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
