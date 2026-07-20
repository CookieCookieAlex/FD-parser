"""Match each Yelp reservation to an in-house guest.

Primary key is guest name (surname carries the most signal, since Yelp's
Guest Details column is inconsistently ordered -- "Guest H" on the
guest list vs. "GUEST H" on Yelp, sometimes surname-only), scoped
to guests in-house on the reservation's date (arrival <= date < departure).
Room and time are secondary signals checked AFTER a name match is found:
they confirm or flag the match, they don't drive it. This matters because
staff-typed room hints in Notes & Tags are themselves handwritten and can be
wrong or stale -- treating them as the primary key would silently trust a
possibly-wrong field over the guest's actual name.

When the matched guest belongs to a multi-room group booking (see
room_groups.py) -- e.g. Guest H has two rooms (WTFACE/TREE) for
the identical stay -- a name+date match doesn't need to resolve to one
specific room to be usable; MatchResult.linked_group carries the other
rooms so the report can show "linked, N rooms" instead of leaving the
reservation ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from fd_reader.match._dates import parse_mmddyyyy, parse_source_date
from fd_reader.match.room_groups import find_room_groups, group_for_guest
from fd_reader.models import GuestRecord
from fd_reader.parse_reservations import ReservationRecord
from fd_reader.room_aliases import resolve_room_code_hint

# Below this rapidfuzz token_sort_ratio score, a name pair is not
# considered a candidate match at all.
FUZZY_NAME_THRESHOLD = 72
# At or above this score the match is confident enough to accept without
# flagging as ambiguous, PROVIDED it beats the next-best candidate by
# AMBIGUITY_MARGIN.
AMBIGUITY_MARGIN = 8


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
    # room_groups.find_room_groups), the other GuestRecords in that group --
    # so a match found by name+date doesn't need to be pinned to one
    # specific room to be usable; the report can show "this is one of N
    # linked rooms" instead of leaving it ambiguous.
    linked_group: list[GuestRecord] = field(default_factory=list)


def _guest_in_house_on(guest: GuestRecord, day: date) -> bool:
    arrival = parse_mmddyyyy(guest.arrival_date)
    departure = parse_mmddyyyy(guest.departure_date)
    if arrival is None or departure is None:
        return False
    return arrival <= day < departure


def match_reservations(
    guests: list[GuestRecord], reservations: list[ReservationRecord]
) -> list[MatchResult]:
    results: list[MatchResult] = []

    groups = find_room_groups(guests)
    groups_by_confirmation = {
        record.confirmation_number: group
        for group in groups
        for record in group.records
    }

    for reservation in reservations:
        res_date = parse_source_date(reservation.source_date)
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
                for r in ([best_guest] + group_for_guest(best_guest, groups_by_confirmation))
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
                linked_group=group_for_guest(best_guest, groups_by_confirmation),
            )
        )

    return results
