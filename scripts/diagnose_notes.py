"""Local-only diagnostic: for a real arrivals PDF, print which guests have
non-empty note fields (guest_notes / reservation_notes / comments_notes)
and their sofa-bed-request detection result -- WITHOUT printing any guest
name, room, or note text itself, so this is safe to run against real
guest-notes/ PDFs and paste the output back for debugging.

Usage:
    .venv/bin/python scripts/diagnose_notes.py path/to/arrivals.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run this both from the project root and as `python scripts/diagnose_notes.py`
# without needing PYTHONPATH set manually.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fd_reader.match.sofa_bed_check import requests_sofa_bed  # noqa: E402
from fd_reader.parsing.guests import parse_guest_pdf  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: diagnose_notes.py path/to/arrivals.pdf", file=sys.stderr)
        sys.exit(1)

    guests = parse_guest_pdf(sys.argv[1])
    print(f"Parsed {len(guests)} guest record(s).\n")

    for i, guest in enumerate(guests, start=1):
        print(f"--- Guest #{i} (confirmation ending ...{guest.confirmation_number[-4:] if guest.confirmation_number else '????'}) ---")
        print(f"  room_name: {guest.room_name!r}")
        print(f"  guest_notes: {'<empty>' if not guest.guest_notes else f'{len(guest.guest_notes)} chars'}")
        print(f"  reservation_notes: {'<empty>' if not guest.reservation_notes else f'{len(guest.reservation_notes)} chars'}")
        print(f"  comments_notes: {'<empty>' if not guest.comments_notes else f'{len(guest.comments_notes)} chars'}")
        print(f"  requests_sofa_bed: {requests_sofa_bed(guest)}")
        if guest.flags:
            print(f"  flags: {guest.flags}")
        print()


if __name__ == "__main__":
    main()
