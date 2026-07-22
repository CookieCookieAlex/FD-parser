"""Compare what a guest's free-text notes say about restaurant reservations
against what Yelp actually shows for that guest. Covers four cases: note
mentions a reservation Yelp doesn't have; Yelp has a reservation the notes
don't mention; both exist but the date/time disagree; neither exists.

Weekday-only notes (e.g. "FRIDAY ARTISANS 7PM") can be ambiguous on a long
stay if the weekday occurs more than once in the window (see parse_notes.py)
-- resolved here using the guest's actual Yelp reservations when exactly one
candidate date has a matching reservation.
"""
from __future__ import annotations

from dataclasses import dataclass

from fd_reader.match._dates import note_time_matches, parse_source_date
from fd_reader.match.name_matching import MatchResult
from fd_reader.models import GuestRecord
from fd_reader.parsing.notes import NoteMention, extract_note_mentions
from fd_reader.parsing.reservations import ReservationRecord

NOTE_FIELDS = ("guest_notes", "reservation_notes", "comments_notes")


@dataclass
class NoteCrossCheck:
    guest: GuestRecord
    mention: NoteMention | None
    reservation: ReservationRecord | None
    status: str  # "matched" / "note_without_reservation" / "reservation_without_note" / "mismatch" / "time_mismatch"
    detail: str = ""


def _resolve_ambiguous_mention(
    mention: NoteMention, guest_reservations: list[ReservationRecord]
) -> NoteMention:
    if not mention.is_ambiguous_weekday or not mention.candidate_dates:
        return mention

    matching_dates = {
        parse_source_date(r.source_date)
        for r in guest_reservations
        if r.restaurant == mention.restaurant
        and parse_source_date(r.source_date) in mention.candidate_dates
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


def _find_same_date_other_restaurant(
    mention: NoteMention, guest_reservations: list[ReservationRecord], used_reservations: set[int]
) -> ReservationRecord | None:
    matches = [
        r for r in guest_reservations
        if id(r) not in used_reservations
        and parse_source_date(r.source_date) == mention.resolved_date
        and r.restaurant != mention.restaurant
    ]
    return matches[0] if matches else None


def _find_same_restaurant_other_date(
    mention: NoteMention, guest_reservations: list[ReservationRecord], used_reservations: set[int]
) -> ReservationRecord | None:
    matches = [
        r for r in guest_reservations
        if id(r) not in used_reservations and r.restaurant == mention.restaurant
    ]
    return matches[0] if matches else None


def _check_mention(
    guest: GuestRecord,
    mention: NoteMention,
    guest_reservations: list[ReservationRecord],
    used_reservations: set[int],
) -> NoteCrossCheck:
    if mention.resolved_date is not None:
        for reservation in guest_reservations:
            if id(reservation) in used_reservations:
                continue
            if reservation.restaurant != mention.restaurant:
                continue
            if parse_source_date(reservation.source_date) != mention.resolved_date:
                continue
            used_reservations.add(id(reservation))
            # Same restaurant + date, but if the note actually names a time
            # and it disagrees with Yelp's, that's worth a flag rather than
            # silently calling it a clean match -- if the note has no
            # parseable time at all, there's nothing to compare, so it
            # stays a clean match.
            if mention.time_text and not note_time_matches(mention.time_text, reservation.time):
                return NoteCrossCheck(
                    guest=guest, mention=mention, reservation=reservation, status="time_mismatch",
                    detail=(
                        f"Guest Notes says {mention.time_text} for {mention.restaurant} on "
                        f"{mention.resolved_date}, but the Yelp reservation on file is at "
                        f"{reservation.time} -- please verify"
                    ),
                )
            return NoteCrossCheck(guest=guest, mention=mention, reservation=reservation, status="matched")

        # No exact match -- check for a likely staff entry error (same date,
        # different restaurant / same restaurant, different date) before
        # concluding the reservation is simply missing.
        conflicting = _find_same_date_other_restaurant(mention, guest_reservations, used_reservations)
        if conflicting is not None:
            used_reservations.add(id(conflicting))
            return NoteCrossCheck(
                guest=guest, mention=mention, reservation=conflicting, status="mismatch",
                detail=(
                    f"Guest Notes says {mention.restaurant} on {mention.resolved_date}, but the "
                    f"Yelp reservation found on that date is at {conflicting.restaurant} "
                    f"instead -- likely a note entry error, needs staff review"
                ),
            )

        conflicting = _find_same_restaurant_other_date(mention, guest_reservations, used_reservations)
        if conflicting is not None:
            used_reservations.add(id(conflicting))
            return NoteCrossCheck(
                guest=guest, mention=mention, reservation=conflicting, status="mismatch",
                detail=(
                    f"Guest Notes says {mention.restaurant} on {mention.resolved_date}, but the "
                    f"guest's Yelp reservation at {conflicting.restaurant} is on "
                    f"{conflicting.source_date} instead -- likely a note entry error, "
                    f"needs staff review"
                ),
            )

    return NoteCrossCheck(
        guest=guest, mention=mention, reservation=None, status="note_without_reservation",
        detail="",
    )


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
                _resolve_ambiguous_mention(m, guest_reservations) for m in raw_mentions
            )

        used_reservations: set[int] = set()

        for mention in mentions:
            checks.append(_check_mention(guest, mention, guest_reservations, used_reservations))

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
