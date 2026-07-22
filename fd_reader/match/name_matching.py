"""Match each Yelp reservation to an in-house guest.

Primary key is guest name, scoped to guests in-house on the reservation's
date (arrival <= date < departure). Room and time are secondary signals
checked AFTER a name match is found -- they confirm or flag the match, they
don't drive it, since staff-typed room hints in Notes & Tags can themselves
be wrong or stale.

When the matched guest belongs to a multi-room group booking (room_groups.py),
a name+date match doesn't need to resolve to one specific room to be usable;
MatchResult.linked_group carries the other rooms.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from fd_reader.match._dates import note_time_matches, parse_mmddyyyy, parse_source_date
from fd_reader.match.room_groups import RoomGroup, find_room_groups, group_for_guest
from fd_reader.models import GuestRecord
from fd_reader.parsing.notes import extract_note_mentions
from fd_reader.parsing.reservations import ReservationRecord
from fd_reader.rooms.aliases import resolve_room_code_hint

# Same three GuestRecord free-text fields notes_cross_check.py scans;
# duplicated here (not imported) to avoid a circular import, since
# notes_cross_check.py imports MatchResult from this module.
_NOTE_FIELDS = ("guest_notes", "reservation_notes", "comments_notes")

# Below this rapidfuzz token_sort_ratio score, a name pair is not
# considered a candidate match at all.
FUZZY_NAME_THRESHOLD = 72
# At or above this score the match is confident enough to accept without
# flagging as ambiguous, PROVIDED it beats the next-best candidate by
# AMBIGUITY_MARGIN.
AMBIGUITY_MARGIN = 8
# When both sides have a first and last name, EACH component must
# independently score at least this well -- see _surnames_agree()/
# _first_names_agree().
NAME_COMPONENT_AGREEMENT_THRESHOLD = 85


def _full_name_variants(name: str) -> list[str]:
    """Both 'Last, First' and 'First Last' forms of a name, normalized, so
    fuzzy matching isn't sensitive to which order either side used."""
    name = name.strip()
    variants = [name]
    if "," in name:
        last, _, first = name.partition(",")
        variants.append(f"{first.strip()} {last.strip()}")
    else:
        parts = name.split()
        if len(parts) >= 2:
            variants.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
    return [v.lower().strip() for v in variants if v.strip()]


def _is_bare_name(name: str) -> bool:
    """True if `name` is a single bare token with no first name at all
    (e.g. Yelp's real "HANKS" rows) -- the surname-only fallback case,
    checked before treating a name as a normal "has a first name" pair."""
    name = name.strip()
    if "," in name:
        return False  # "Last, First" always has a first name present
    return len(name.split()) == 1


def _surname(name: str) -> str | None:
    """The surname from any name shape (bare, 'First Last', or
    'Last, First')."""
    name = name.strip()
    if not name:
        return None
    if "," in name:
        last, _, _first = name.partition(",")
        return last.strip().lower() or None
    parts = name.split()
    if not parts:
        return None
    return parts[-1].lower().strip()  # bare, or "First Last" -- surname is the last token


def _strip_initial_punctuation(token: str) -> str:
    """Strips periods so dotted initials compare correctly (e.g. "C.J."
    vs "CJ")."""
    return re.sub(r"\.", "", token)


def _extract_first_name(name: str) -> str | None:
    """The first token of the first-name portion, from any name shape, or
    None if `name` is bare (only a surname) or empty. Only the first token
    -- not a middle initial/name too -- so a middle initial on one side
    (e.g. "Annabelle K") doesn't drag the score down against a bare
    first name on the other."""
    name = name.strip()
    if not name:
        return None
    if "," in name:
        _last, _, first = name.partition(",")
        first = first.strip()
        return _strip_initial_punctuation(first.split()[0].lower()) if first else None
    parts = name.split()
    if len(parts) < 2:
        return None  # bare surname -- no first name to compare
    return _strip_initial_punctuation(parts[0].lower().strip())  # "First [Middle] Last" -- first token only


def _surnames_agree(guest_name: str, yelp_name: str) -> bool:
    """When both sides carry a first name, their surnames must
    independently score well against each other -- not just the combined
    full-name string, since a shared first name (e.g. "laura hanks" vs
    "laura adams") can otherwise keep the combined score deceptively high
    even when the surnames share almost nothing."""
    if _is_bare_name(yelp_name):
        return True  # bare-surname Yelp row -- handled separately, not gated here

    guest_surname = _surname(guest_name)
    yelp_surname = _surname(yelp_name)
    if guest_surname is None or yelp_surname is None:
        return True  # nothing to gate on if either side has no surname at all

    return fuzz.token_sort_ratio(guest_surname, yelp_surname) >= NAME_COMPONENT_AGREEMENT_THRESHOLD


def _first_names_agree(guest_name: str, yelp_name: str) -> bool:
    """Symmetric to _surnames_agree(): a matching surname alone isn't
    enough either -- two unrelated people can share a surname (e.g.
    "Cyrus, Sophia" vs. an unrelated "John Cyrus"), so the first names
    must also independently agree."""
    if _is_bare_name(yelp_name):
        return True  # bare-surname Yelp row -- no first name to gate on at all

    guest_first = _extract_first_name(guest_name)
    yelp_first = _extract_first_name(yelp_name)
    if guest_first is None or yelp_first is None:
        return True  # nothing to gate on if either side has no first name

    return fuzz.token_sort_ratio(guest_first, yelp_first) >= NAME_COMPONENT_AGREEMENT_THRESHOLD


def _best_name_score(guest_name: str, yelp_name: str) -> int:
    """Compares full "First Last"/"Last, First" forms on both sides.

    Guest names are always "Last, First" and never bare, so there's no
    guest-side surname-only fallback -- only a genuinely surname-only
    Yelp row (e.g. "HANKS") falls back to comparing surnames alone. A
    name that has a first name must always be judged on it, or two
    different people sharing a surname could both score a false 100
    against one guest.

    Both _surnames_agree() and _first_names_agree() must pass (return 0
    outright otherwise) -- agreement on only one name component is common
    across unrelated people and isn't reliable signal by itself."""
    if not _surnames_agree(guest_name, yelp_name):
        return 0
    if not _first_names_agree(guest_name, yelp_name):
        return 0

    guest_variants = _full_name_variants(guest_name)
    yelp_variants = _full_name_variants(yelp_name)
    best = 0
    for g in guest_variants:
        for y in yelp_variants:
            score = fuzz.token_sort_ratio(g, y)
            best = max(best, score)

    if _is_bare_name(yelp_name):
        yelp_surname = _surname(yelp_name)
        guest_surname = guest_name.strip().partition(",")[0].strip().lower()
        if yelp_surname and guest_surname:
            score = fuzz.token_sort_ratio(guest_surname, yelp_surname)
            best = max(best, score)

    return best


def _guest_has_matching_note(
    guest: GuestRecord, restaurant: str | None, res_date: date, reservation_time: str
) -> bool:
    """Whether `guest`'s free-text notes mention `restaurant` on `res_date`
    (directly, or as one candidate of an ambiguous weekday mention) with a
    time that agrees with the reservation's actual time -- used to break a
    name-match tie between candidates, per CLAUDE.md's "flag, don't guess"
    rule this only narrows down, never replaces, the ambiguity flag."""
    if restaurant is None:
        return False
    for field_name in _NOTE_FIELDS:
        text = getattr(guest, field_name)
        for mention in extract_note_mentions(text, field_name, guest.arrival_date, guest.departure_date):
            if mention.restaurant != restaurant:
                continue
            date_matches = mention.resolved_date == res_date or res_date in mention.candidate_dates
            if date_matches and note_time_matches(mention.time_text, reservation_time):
                return True
    return False


@dataclass
class MatchResult:
    reservation: ReservationRecord
    guest: GuestRecord | None
    match_method: str  # "name" / "none"
    confidence: int | None = None  # fuzzy-name score, when applicable
    flags: list[str] = field(default_factory=list)
    linked_group: list[GuestRecord] = field(default_factory=list)  # other rooms in the same group booking
    # Other guests this reservation could plausibly belong to, when an
    # "ambiguous_name_match"/tie was resolved by attaching to the top-
    # scoring candidate rather than left unmatched (see match_reservations).
    other_candidates: list[GuestRecord] = field(default_factory=list)


def _guest_in_house_on(guest: GuestRecord, day: date) -> bool:
    arrival = parse_mmddyyyy(guest.arrival_date)
    departure = parse_mmddyyyy(guest.departure_date)
    if arrival is None or departure is None:
        return False
    return arrival <= day < departure


def match_reservations(
    guests: list[GuestRecord],
    reservations: list[ReservationRecord],
    groups: list[RoomGroup] | None = None,
) -> list[MatchResult]:
    """`groups` lets a caller that's already computed find_room_groups(guests)
    (e.g. the CLI/app pipeline, which also needs it for build_guest_blocks
    and the group-booking count) pass it in instead of recomputing it here."""
    results: list[MatchResult] = []

    if groups is None:
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

        # A tie among candidates that all belong to the same linked room
        # group isn't a real ambiguity -- one guest, several rooms.
        # Collapse it to a single match, with the rest as linked_group.
        tied_group = groups_by_confirmation.get(tied_top[0].confirmation_number)
        tied_all_same_group = (
            tied_group is not None
            and {g.confirmation_number for g in tied_top}
            <= {r.confirmation_number for r in tied_group.records}
        )

        is_tied = len(tied_top) > 1 and not tied_all_same_group
        is_near_tie = len(scored) > 1 and not tied_all_same_group and (
            top_score - scored[1][1] < AMBIGUITY_MARGIN
        )

        if is_tied or is_near_tie:
            # Real ambiguity: more than one in-house guest is a plausible
            # match by name alone. Before giving up, see if exactly one of
            # them has a note mentioning this restaurant/date/time -- if
            # so, that resolves it. Otherwise attach to the top-scoring
            # candidate (never guessed silently -- still flagged, with the
            # rest listed as other_candidates for the report to show).
            ambiguous_candidates = tied_top if is_tied else [g for g, s in scored if top_score - s < AMBIGUITY_MARGIN]
            note_matches = [
                g for g in ambiguous_candidates
                if _guest_has_matching_note(g, reservation.restaurant, res_date, reservation.time)
            ]

            if len(note_matches) == 1:
                best_guest = note_matches[0]
                others = [g for g in ambiguous_candidates if g is not best_guest]
                tie_flags = ["resolved_by_note_time"]
            else:
                best_guest = ambiguous_candidates[0]
                others = ambiguous_candidates[1:]
                tie_flags = ["ambiguous_name_match"]

            results.append(
                MatchResult(
                    reservation=reservation,
                    guest=best_guest,
                    match_method="name",
                    confidence=top_score,
                    flags=tie_flags,
                    linked_group=group_for_guest(best_guest, groups_by_confirmation),
                    other_candidates=others,
                )
            )
            continue

        best_guest = tied_top[0]
        flags: list[str] = []

        # Room is a secondary confirm/flag signal: if Notes & Tags has a
        # resolvable room hint, flag if it disagrees with the matched
        # guest's actual room (stale/mistyped note, or a genuine room
        # change) rather than trusting either side silently.
        hinted_room = resolve_room_code_hint(reservation.room_code_hint)
        if hinted_room is not None and best_guest.room_name:
            group_room_codes = {
                r.room_name.strip().upper()
                for r in ([best_guest] + group_for_guest(best_guest, groups_by_confirmation))
                if r.room_name
            }
            if hinted_room.abbreviation not in group_room_codes:
                flags.append("room_mismatch")

        # Flag what's actually identifying this match: a full name match
        # with no room hint is a softer issue (YELLOW) than a bare-surname
        # match with no room hint (RED -- could be an unrelated person who
        # just shares a surname with someone in-house).
        if hinted_room is None:
            if _is_bare_name(reservation.guest_name):
                flags.append("surname_only_no_room_hint")
            else:
                flags.append("no_room_hint")

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
