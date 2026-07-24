from dataclasses import dataclass, field


@dataclass
class GuestRecord:
    confirmation_number: str
    guest_name: str
    room_name: str
    room_type: str
    status: str
    arrival_date: str
    departure_date: str
    guests_count: int | None
    guests_share: int | None
    source_page: int

    rate_plan: str = ""

    vip_level: str = ""
    address: str = ""
    preferences: str = ""
    last_stay_property: str = ""
    last_checkout_date: str = ""
    lifetime_revenue: str = ""
    lifetime_stays: str = ""
    lifetime_nights: str = ""
    booking_agency: str = ""
    iata: str = ""
    guest_notes: str = ""
    reservation_notes: str = ""
    comments_notes: str = ""

    flags: list[str] = field(default_factory=list)


# The three free-text note fields, in the order they appear on the arrivals
# report (see CLAUDE.md: Guest Notes / Reservation Notes / Comments-Notes).
NOTE_FIELDS = ("guest_notes", "reservation_notes", "comments_notes")


def all_notes_text(guest: "GuestRecord") -> str:
    """Concatenate all three free-text note fields for a single regex/keyword
    scan, used by checks that don't care which field a mention came from."""
    return " ".join(getattr(guest, field_name) or "" for field_name in NOTE_FIELDS)
