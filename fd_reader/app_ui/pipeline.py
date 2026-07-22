"""Parse -> match -> cross-check pipeline, cached and driven from either a
folder path or uploaded files. The only module in the app package that
touches disk/tempfile; formatting.py and card.py just consume its output.
"""
from __future__ import annotations

import os
import tempfile

import streamlit as st

from fd_reader.cli import _discover_pdfs
from fd_reader.match import cross_check_notes, detect_room_moves, find_room_groups, match_reservations
from fd_reader.models import GuestRecord
from fd_reader.parsing.guests import parse_guest_pdf
from fd_reader.parsing.reservations import parse_reservation_pdf
from fd_reader.report import GuestBlock, ReservationLine, RED, build_guest_blocks


def _split_duplicate_confirmations(
    guests: list[GuestRecord],
) -> tuple[list[GuestRecord], list[GuestRecord]]:
    """Pulls out every repeat guest record whose confirmation_number was
    already seen earlier in this loaded set, returning (clean_guests,
    duplicate_guests). The first occurrence of a confirmation number is
    kept in clean_guests and processed normally; every later occurrence
    is treated as unusable.

    confirmation_number is the identity key every other part of the app
    (match results, room moves, group bookings, card.py's widget keys)
    assumes is unique per render -- this should never happen. But it's a
    real, reachable case: e.g. the same arrivals PDF loaded twice, or two
    overlapping-date exports that both include the same stay. First-seen
    is an arbitrary but deterministic tiebreak (file/page order), not a
    claim that the first copy is more likely to be correct.

    Each pulled-out copy still gets its own placeholder card (see
    pipeline._run_pipeline / card.py), it's just not processed."""
    counts: dict[str, int] = {}
    for guest in guests:
        if guest.confirmation_number:
            counts[guest.confirmation_number] = counts.get(guest.confirmation_number, 0) + 1

    clean, duplicates = [], []
    seen: set[str] = set()
    for guest in guests:
        conf = guest.confirmation_number
        if conf and counts[conf] > 1:
            if conf in seen:
                duplicates.append(guest)
            else:
                seen.add(conf)
                clean.append(guest)
        else:
            clean.append(guest)
    return clean, duplicates


def _duplicate_placeholder_block(guest: GuestRecord, occurrences: int) -> GuestBlock:
    """A minimal, unprocessed GuestBlock for a guest excluded by
    _split_duplicate_confirmations -- no Yelp matching, note cross-check,
    room-move, or group-booking data, since none of that ran for it. The
    first-seen copy with this confirmation number was kept and processed
    normally elsewhere in the guest list -- see that card instead."""
    note = (
        f"Duplicate confirmation number ({guest.confirmation_number}): this "
        f"reservation appears {occurrences} times in the loaded PDFs -- e.g. the "
        "same arrivals PDF loaded twice, or two overlapping exports. This copy was "
        "not matched against Yelp or notes -- the first copy found was processed "
        "instead; look for that card. Please resolve the duplicate in the source "
        "data and reload."
    )
    return GuestBlock(
        guest=guest,
        lines=[ReservationLine(color=RED, note="Not processed -- duplicate confirmation number.")],
        duplicate_id_note=note,
    )


def _mtime_fingerprint(paths: tuple[str, ...]) -> tuple[float, ...]:
    """Per-path last-modified time, included in _run_pipeline's cache key
    so re-saving a PDF to the same path (e.g. "Folder path" mode, where
    the path stays constant across reloads) invalidates the cache instead
    of silently serving stale parsed results. Upload mode isn't at risk
    either way -- tempfile.TemporaryDirectory mints a fresh random path
    per upload -- but the fingerprint is harmless there too."""
    return tuple(os.path.getmtime(p) for p in paths)


@st.cache_data(show_spinner=False)
def _run_pipeline(
    guest_paths: tuple[str, ...],
    yelp_paths: tuple[str, ...],
    _guest_mtimes: tuple[float, ...],
    _yelp_mtimes: tuple[float, ...],
) -> tuple[list[GuestBlock], int, int]:
    guests = []
    for path in guest_paths:
        guests.extend(parse_guest_pdf(path))

    reservations = []
    for path in yelp_paths:
        reservations.extend(parse_reservation_pdf(path))

    guests, duplicate_guests = _split_duplicate_confirmations(guests)

    room_groups = find_room_groups(guests)
    match_results = match_reservations(guests, reservations, room_groups)
    note_checks = cross_check_notes(guests, match_results)
    room_moves = detect_room_moves(guests)

    blocks = build_guest_blocks(guests, match_results, note_checks, room_moves, room_groups)

    if duplicate_guests:
        occurrences: dict[str, int] = {}
        for guest in duplicate_guests:
            occurrences[guest.confirmation_number] = occurrences.get(guest.confirmation_number, 0) + 1
        blocks = blocks + [
            _duplicate_placeholder_block(guest, occurrences[guest.confirmation_number])
            for guest in duplicate_guests
        ]

    return blocks, len(room_moves), len(room_groups)


def _load_from_folder(folder: str) -> tuple[list[GuestBlock], int, int] | None:
    if not folder or not os.path.isdir(folder):
        st.warning("Enter a valid folder path.")
        return None
    guest_paths, yelp_paths = _discover_pdfs(folder)
    if not guest_paths:
        st.error("No arrivals-report PDF found in that folder (looked for 'Arrivals with Details').")
        return None
    if not yelp_paths:
        st.error("No Yelp reservation PDFs found in that folder.")
        return None
    guest_paths, yelp_paths = tuple(guest_paths), tuple(yelp_paths)
    return _run_pipeline(
        guest_paths, yelp_paths, _mtime_fingerprint(guest_paths), _mtime_fingerprint(yelp_paths)
    )


def _load_from_uploads(uploaded_files) -> tuple[list[GuestBlock], int, int] | None:
    if not uploaded_files:
        return None

    # _run_pipeline parses the PDFs into plain dataclasses and returns
    # (cached by path), so the on-disk copies aren't needed once it
    # returns -- clean the temp dir up immediately rather than leaking a
    # fresh copy of real guest PDFs on every click (see CLAUDE.md's guest
    # PII confidentiality note).
    with tempfile.TemporaryDirectory(prefix="fd_reader_upload_") as tmp_dir:
        for uploaded in uploaded_files:
            with open(os.path.join(tmp_dir, uploaded.name), "wb") as f:
                f.write(uploaded.getbuffer())

        guest_paths, yelp_paths = _discover_pdfs(tmp_dir)
        if not guest_paths:
            st.error("No arrivals-report PDF found among the uploaded files.")
            return None
        if not yelp_paths:
            st.error("No Yelp reservation PDFs found among the uploaded files.")
            return None
        guest_paths, yelp_paths = tuple(guest_paths), tuple(yelp_paths)
        return _run_pipeline(
            guest_paths, yelp_paths, _mtime_fingerprint(guest_paths), _mtime_fingerprint(yelp_paths)
        )
