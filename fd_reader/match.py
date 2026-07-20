"""Cross-check the guest-arrivals list against Yelp restaurant reservations.

Two independent things happen here, both described in CLAUDE.md's
"Matching strategy" and "Guest-list data-quality checks" sections:

1. Guest <-> Yelp matching: for each Yelp ReservationRecord, find which
   in-house GuestRecord it belongs to. Primary key is guest name
   (surname-led, date-scoped to who's in-house that day); room and time
   are secondary confirm/flag signals checked AFTER the guest is already
   decided by name, never used to pick who the guest is. This answers
   "does this Yelp reservation correspond to a real in-house guest, and
   does everything else about it (room, party size) line up?"

2. Notes <-> Yelp cross-check: for each GuestRecord, extract restaurant
   mentions out of its free-text note fields (fd_reader.parse_notes) and
   compare them against the Yelp reservations actually found for that
   guest. This answers "does what staff wrote in the guest notes actually
   match what's in Yelp?" -- covering all four cases: note mentions a
   reservation Yelp doesn't have; Yelp has a reservation the notes don't
   mention; both exist but the date/time disagree; neither exists (no
   dinner reservation at all, not a problem by itself).

   The weekday-only notes (one staff member's all-caps style, e.g. "FRIDAY
   ARTISANS 7PM") can be genuinely ambiguous on a long stay (the weekday
   occurs more than once in the stay window -- see parse_notes.py). Per
   the user, this ambiguity should be resolved using the guest's actual
   Yelp reservations: if exactly one of the note's candidate_dates has a
   matching Yelp reservation (same restaurant, same guest) that resolves
   the ambiguity outright instead of leaving it permanently unresolved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from rapidfuzz import fuzz

from fd_reader.models import GuestRecord
from fd_reader.parse_notes import NoteMention, extract_note_mentions
from fd_reader.parse_reservations import ReservationRecord
from fd_reader.room_aliases import resolve_room_code_hint

NOTE_FIELDS = ("guest_notes", "reservation_notes", "comments_notes")

# Below this rapidfuzz token_sort_ratio score, a name pair is not
# considered a candidate match at all.
FUZZY_NAME_THRESHOLD = 72
# At or above this score the match is confident enough to accept without
# flagging as ambiguous, PROVIDED it beats the next-best candidate by
# AMBIGUITY_MARGIN.
AMBIGUITY_MARGIN = 8


def _parse_mmddyyyy(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except (ValueError, AttributeError):
        return None


def _parse_source_date(text: str) -> date | None:
    """ReservationRecord.source_date is like 'Jun 20, 2026' (see
    parse_reservations.py's _find_date_from_filter_bar)."""
    try:
        return datetime.strptime(text.strip(), "%b %d, %Y").date()
    except (ValueError, AttributeError):
        return None


def _name_variants(name: str) -> list[str]:
    """Both 'Last, First' and 'First Last' forms, normalized, so fuzzy
    matching isn't sensitive to which order either side used. Also emits
    a surname-only variant, since Yelp rows sometimes have only a surname
    (e.g. 'GUEST B')."""
    name = name.strip()
    variants = [name]
    if "," in name:
        last, _, first = name.partition(",")
        variants.append(f"{first.strip()} {last.strip()}")
        variants.append(last.strip())
    else:
        parts = name.split()
        if len(parts) >= 2:
            variants.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
            variants.append(parts[-1])
    return [v.lower().strip() for v in variants if v.strip()]


def _best_name_score(guest_name: str, yelp_name: str) -> int:
    guest_variants = _name_variants(guest_name)
    yelp_variants = _name_variants(yelp_name)
    best = 0
    for g in guest_variants:
        for y in yelp_variants:
            score = fuzz.token_sort_ratio(g, y)
            best = max(best, score)
    return best


@dataclass
class MatchResult:
    reservation: ReservationRecord
    guest: GuestRecord | None
    match_method: str  # "name" / "none"
    confidence: int | None = None  # fuzzy-name score, when applicable
    flags: list[str] = field(default_factory=list)
    # When the matched guest belongs to a multi-room group booking (see
    # find_room_groups), the other GuestRecords in that group -- so a
    # match found by name+date doesn't need to be pinned to one specific
    # room to be usable; the report can show "this is one of N linked
    # rooms" instead of leaving it ambiguous.
    linked_group: list[GuestRecord] = field(default_factory=list)


@dataclass
class RoomGroup:
    """Multiple GuestRecords booked into several rooms at once for the
    same [arrival_date, departure_date] -- a family/party booking.
    Distinct from a room move (RoomMove, below) -- these stays overlap
    completely rather than chaining end-to-end.

    matched_by tells you WHY these records were linked:
      - "exact_name": identical guest_name (confirmed real: Guest B,
        Guest B across TAHAW/AMPER/MTJO; Guest H across
        WTFACE/TREE; Guest J across HAWK/LOON) -- high confidence.
      - "same_surname": same surname, same dates, but a DIFFERENT first
        name (e.g. "Guest X" and "Guest Y" arriving/departing
        together) -- also a family booking, per the user, but a softer
        signal than an identical name match since two unrelated guests
        could in principle share a surname and dates by coincidence.
        Not yet confirmed in the real sample data (no such case exists
        there as of this writing) -- added defensively per user request,
        not from an observed bug.
    """
    guest_name: str
    records: list[GuestRecord]
    matched_by: str = "exact_name"


def _surname(guest_name: str) -> str:
    """Guest-list names are consistently 'Last, First' (confirmed: every
    real sample-data name has a comma) -- take the part before the comma.
    Falls back to the last whitespace-separated token for any name that
    doesn't follow that format, rather than guessing wrong."""
    name = guest_name.strip()
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    parts = name.split()
    return parts[-1].strip().lower() if parts else name.lower()


def find_room_groups(guests: list[GuestRecord]) -> list[RoomGroup]:
    exact_key_to_records: dict[tuple[str, str, str], list[GuestRecord]] = {}
    for guest in guests:
        key = (guest.guest_name.strip().lower(), guest.arrival_date, guest.departure_date)
        exact_key_to_records.setdefault(key, []).append(guest)

    groups: list[RoomGroup] = []
    grouped_confirmations: set[str] = set()
    for records in exact_key_to_records.values():
        if len(records) > 1:
            groups.append(RoomGroup(guest_name=records[0].guest_name, records=records, matched_by="exact_name"))
            grouped_confirmations.update(r.confirmation_number for r in records)

    # Same surname + same dates, different first name -- only consider
    # guests not already claimed by an exact-name group above, so a
    # 3-room exact-name family isn't also re-grouped here.
    surname_key_to_records: dict[tuple[str, str, str], list[GuestRecord]] = {}
    for guest in guests:
        if guest.confirmation_number in grouped_confirmations:
            continue
        key = (_surname(guest.guest_name), guest.arrival_date, guest.departure_date)
        surname_key_to_records.setdefault(key, []).append(guest)

    for records in surname_key_to_records.values():
        # Require at least two DISTINCT first names -- if it's the same
        # guest_name repeated, that's already an exact_name group (or a
        # true duplicate record), not a same-surname case.
        distinct_names = {r.guest_name.strip().lower() for r in records}
        if len(records) > 1 and len(distinct_names) > 1:
            groups.append(RoomGroup(guest_name=records[0].guest_name, records=records, matched_by="same_surname"))

    return groups


def _group_for_guest(
    guest: GuestRecord, groups_by_confirmation: dict[str, RoomGroup]
) -> list[GuestRecord]:
    group = groups_by_confirmation.get(guest.confirmation_number)
    if group is None:
        return []
    return [r for r in group.records if r.confirmation_number != guest.confirmation_number]


@dataclass
class NoteCrossCheck:
    guest: GuestRecord
    mention: NoteMention | None
    reservation: ReservationRecord | None
    status: str  # "matched" / "note_without_reservation" / "reservation_without_note" / "mismatch"
    detail: str = ""


def _guest_in_house_on(guest: GuestRecord, day: date) -> bool:
    arrival = _parse_mmddyyyy(guest.arrival_date)
    departure = _parse_mmddyyyy(guest.departure_date)
    if arrival is None or departure is None:
        return False
    return arrival <= day < departure


def match_reservations(
    guests: list[GuestRecord], reservations: list[ReservationRecord]
) -> list[MatchResult]:
    """Match each Yelp reservation to an in-house guest.

    Primary key is guest name (surname carries the most signal, since
    Yelp's Guest Details column is inconsistently ordered -- "Guest H,
    Guest H" on the guest list vs. "GUEST H" on Yelp, sometimes
    surname-only), scoped to guests in-house on the reservation's date
    (arrival <= date < departure). Room and time are secondary signals
    checked AFTER a name match is found: they confirm or flag the match,
    they don't drive it. This matters because staff-typed room hints in
    Notes & Tags are themselves handwritten and can be wrong or stale --
    treating them as the primary key would silently trust a possibly-wrong
    field over the guest's actual name.

    When the matched guest belongs to a multi-room group booking (see
    find_room_groups) -- e.g. Guest H has two rooms
    (WTFACE/TREE) for the identical stay -- a name+date match doesn't need
    to resolve to one specific room to be usable; MatchResult.linked_group
    carries the other rooms so the report can show "linked, N rooms"
    instead of leaving the reservation ambiguous.
    """
    results: list[MatchResult] = []

    groups = find_room_groups(guests)
    groups_by_confirmation: dict[str, RoomGroup] = {}
    for group in groups:
        for record in group.records:
            groups_by_confirmation[record.confirmation_number] = group

    for reservation in reservations:
        res_date = _parse_source_date(reservation.source_date)
        if res_date is None:
            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=None,
                    match_method="none",
                    flags=["unparseable_reservation_date"],
                )
            )
            continue

        if reservation.is_outside_guest:
            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=None,
                    match_method="none",
                    flags=["outside_guest"],
                )
            )
            continue

        candidates = [g for g in guests if _guest_in_house_on(g, res_date)]

        # 1. Name match (surname + first name where present), scoped to
        # guests in-house that day. This is the primary key.
        scored = [
            (g, _best_name_score(g.guest_name, reservation.guest_name))
            for g in candidates
        ]
        scored = [(g, s) for g, s in scored if s >= FUZZY_NAME_THRESHOLD]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        if not scored:
            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=None,
                    match_method="none",
                    flags=["no_match_found"],
                )
            )
            continue

        top_score = scored[0][1]
        tied_top = [g for g, s in scored if s == top_score]

        # A tie among candidates that are all the same linked room-group
        # (e.g. all 3 of Guest B's rooms, or Guest H's 2 rooms) isn't
        # a real ambiguity -- it's one guest under one name+date with
        # several rooms. Collapse it to a single match against the first
        # record, with the rest carried as linked_group.
        tied_group = groups_by_confirmation.get(tied_top[0].confirmation_number)
        tied_all_same_group = (
            tied_group is not None
            and {g.confirmation_number for g in tied_top}
            <= {r.confirmation_number for r in tied_group.records}
        )

        if len(tied_top) > 1 and not tied_all_same_group:
            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=None,
                    match_method="none",
                    confidence=top_score,
                    flags=["ambiguous_name_match"],
                )
            )
            continue
        if len(scored) > 1 and not tied_all_same_group and (
            top_score - scored[1][1] < AMBIGUITY_MARGIN
        ):
            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=None,
                    match_method="none",
                    confidence=top_score,
                    flags=["ambiguous_name_match"],
                )
            )
            continue

        best_guest = tied_top[0]
        flags: list[str] = []

        # 2. Room is a secondary confirm/flag signal, not the match key:
        # if Notes & Tags has a resolvable room hint, check it agrees
        # with the matched guest's actual room. Disagreement is flagged
        # for staff review (could be a stale/mistyped Yelp note, or the
        # guest genuinely changed rooms) rather than silently trusted
        # either way.
        hinted_room = resolve_room_code_hint(reservation.room_code_hint)
        if hinted_room is not None and best_guest.room_name:
            group_room_codes = {
                r.room_name.strip().upper()
                for r in ([best_guest] + _group_for_guest(best_guest, groups_by_confirmation))
                if r.room_name
            }
            if hinted_room.abbreviation not in group_room_codes:
                flags.append("room_mismatch")

        if reservation.party_size is not None and best_guest.guests_count is not None:
            if reservation.party_size != best_guest.guests_count:
                flags.append("party_size_mismatch")

        results.append(
            MatchResult(
                reservation=reservation,
                guest=best_guest,
                match_method="name",
                confidence=top_score,
                flags=flags,
                linked_group=_group_for_guest(best_guest, groups_by_confirmation),
            )
        )

    return results


def _resolve_ambiguous_mention(
    mention: NoteMention, guest: GuestRecord, guest_reservations: list[ReservationRecord]
) -> NoteMention:
    """If a weekday mention was ambiguous (occurs more than once in the
    stay), narrow it down using the guest's actual matched Yelp
    reservations: if exactly one candidate date has a same-restaurant
    reservation, that's the real date."""
    if not mention.is_ambiguous_weekday or not mention.candidate_dates:
        return mention

    matching_dates = {
        _parse_source_date(r.source_date)
        for r in guest_reservations
        if r.restaurant == mention.restaurant
        and _parse_source_date(r.source_date) in mention.candidate_dates
    }
    if len(matching_dates) == 1:
        resolved_date = next(iter(matching_dates))
        return NoteMention(
            restaurant=mention.restaurant,
            resolved_date=resolved_date,
            time_text=mention.time_text,
            source_field=mention.source_field,
            raw_text=mention.raw_text,
            weekday_text=mention.weekday_text,
            is_ambiguous_weekday=False,
            flags=[f for f in mention.flags if f != "ambiguous_weekday"],
            candidate_dates=[],
        )
    return mention


def cross_check_notes(
    guests: list[GuestRecord], match_results: list[MatchResult]
) -> list[NoteCrossCheck]:
    """For every guest, compare what the free-text notes say about
    restaurant reservations against what Yelp actually shows."""
    reservations_by_guest: dict[str, list[ReservationRecord]] = {}
    for result in match_results:
        if result.guest is not None:
            reservations_by_guest.setdefault(
                result.guest.confirmation_number, []
            ).append(result.reservation)

    checks: list[NoteCrossCheck] = []

    for guest in guests:
        guest_reservations = reservations_by_guest.get(guest.confirmation_number, [])

        mentions: list[NoteMention] = []
        for field_name in NOTE_FIELDS:
            text = getattr(guest, field_name)
            raw_mentions = extract_note_mentions(
                text, field_name, guest.arrival_date, guest.departure_date
            )
            mentions.extend(
                _resolve_ambiguous_mention(m, guest, guest_reservations)
                for m in raw_mentions
            )

        used_reservations: set[int] = set()

        for mention in mentions:
            match = None
            if mention.resolved_date is not None:
                for reservation in guest_reservations:
                    if id(reservation) in used_reservations:
                        continue
                    if reservation.restaurant != mention.restaurant:
                        continue
                    if _parse_source_date(reservation.source_date) != mention.resolved_date:
                        continue
                    match = reservation
                    break

            if match is not None:
                used_reservations.add(id(match))
                checks.append(
                    NoteCrossCheck(
                        guest=guest,
                        mention=mention,
                        reservation=match,
                        status="matched",
                    )
                )
                continue

            # No exact (restaurant + date) match -- before giving up, check
            # whether this looks like a human-entry mismatch rather than a
            # true absence: same date but a different restaurant booked
            # (e.g. note says "artisans on 6/28" but the guest's actual
            # Yelp reservation that day is at Maggie's), which is worth
            # surfacing distinctly since it's likely staff error, not a
            # missing reservation.
            if mention.resolved_date is not None:
                same_date_other_restaurant = [
                    r for r in guest_reservations
                    if id(r) not in used_reservations
                    and _parse_source_date(r.source_date) == mention.resolved_date
                    and r.restaurant != mention.restaurant
                ]
                if same_date_other_restaurant:
                    conflicting = same_date_other_restaurant[0]
                    used_reservations.add(id(conflicting))
                    checks.append(
                        NoteCrossCheck(
                            guest=guest,
                            mention=mention,
                            reservation=conflicting,
                            status="mismatch",
                            detail=(
                                f"note says {mention.restaurant} on "
                                f"{mention.resolved_date}, but the Yelp "
                                f"reservation found on that date is at "
                                f"{conflicting.restaurant} instead -- likely "
                                f"a note entry error, needs staff review"
                            ),
                        )
                    )
                    continue

                same_restaurant_other_date = [
                    r for r in guest_reservations
                    if id(r) not in used_reservations and r.restaurant == mention.restaurant
                ]
                if same_restaurant_other_date:
                    conflicting = same_restaurant_other_date[0]
                    used_reservations.add(id(conflicting))
                    checks.append(
                        NoteCrossCheck(
                            guest=guest,
                            mention=mention,
                            reservation=conflicting,
                            status="mismatch",
                            detail=(
                                f"note says {mention.restaurant} on "
                                f"{mention.resolved_date}, but the guest's "
                                f"Yelp reservation at {conflicting.restaurant} "
                                f"is on {conflicting.source_date} instead -- "
                                f"likely a note entry error, needs staff review"
                            ),
                        )
                    )
                    continue

            if mention.resolved_date is None and mention.flags:
                checks.append(
                    NoteCrossCheck(
                        guest=guest,
                        mention=mention,
                        reservation=None,
                        status="note_without_reservation",
                        detail=f"note could not be resolved to a date: {mention.flags}",
                    )
                )
            else:
                checks.append(
                    NoteCrossCheck(
                        guest=guest,
                        mention=mention,
                        reservation=None,
                        status="note_without_reservation",
                        detail="no matching Yelp reservation found for this note mention",
                    )
                )

        for reservation in guest_reservations:
            if id(reservation) in used_reservations:
                continue
            checks.append(
                NoteCrossCheck(
                    guest=guest,
                    mention=None,
                    reservation=reservation,
                    status="reservation_without_note",
                    detail="Yelp reservation found but not mentioned in any guest note field",
                )
            )

    return checks


@dataclass
class RoomMove:
    guest_name: str
    earlier: GuestRecord
    later: GuestRecord


def detect_room_moves(guests: list[GuestRecord]) -> list[RoomMove]:
    """A room move is: same guest name, one record's departure_date
    exactly equals another's arrival_date (no off-by-one tolerance), AND
    both room name and room type change between the two records. If only
    the room name changes but the room type stays the same (e.g. a
    same-category reassignment), it's not treated as a move.

    Records are linked, never merged -- confirmation number is per-stay,
    not per-guest (see room_directory.py's module docstring)."""
    by_name: dict[str, list[GuestRecord]] = {}
    for guest in guests:
        by_name.setdefault(guest.guest_name.strip().lower(), []).append(guest)

    moves: list[RoomMove] = []
    for records in by_name.values():
        if len(records) < 2:
            continue
        for earlier in records:
            for later in records:
                if earlier is later:
                    continue
                if earlier.departure_date != later.arrival_date:
                    continue
                if earlier.room_name == later.room_name:
                    continue
                if earlier.room_type == later.room_type:
                    continue
                moves.append(
                    RoomMove(guest_name=earlier.guest_name, earlier=earlier, later=later)
                )

    return moves
