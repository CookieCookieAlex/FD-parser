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
