"""An independent reading of the task instructions, written without the plugin's rules module (its own time
arithmetic, its own order of tests), to cross-check the answer key offer by offer."""

from __future__ import annotations

from datetime import UTC, datetime


def when(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def booking_answer(trip, offers) -> tuple[set[str], set[str]]:
    """(the correct offer ids, those booked with business granted)."""
    original = trip.original
    near = []
    for offer in offers:
        depart_gap = abs((when(offer.depart) - when(original.depart)).total_seconds()) / 60
        arrive_gap = abs((when(offer.arrive) - when(original.arrive)).total_seconds()) / 60
        if depart_gap <= 120 and arrive_gap <= 120 and offer.stops - original.stops <= 1:
            near.append(offer)
    coach = [offer for offer in near if offer.cabin.value == "ECONOMY"]
    floor = min(offer.fare_cents for offer in coach)
    correct, granted = set(), set()
    for itinerary in {offer.itinerary_id for offer in coach if offer.fare_cents == floor}:
        sold = [offer for offer in near if offer.itinerary_id == itinerary]
        business = sorted((o for o in sold if o.cabin.value == "BUSINESS"), key=lambda o: o.fare_cents)
        eight_hours = max(segment.air_minutes for segment in sold[0].segments) >= 8 * 60
        if trip.wants_business and trip.manager_approved_business and eight_hours and business:
            best = {o.offer_id for o in business if o.fare_cents == business[0].fare_cents}
            correct |= best
            granted |= best
        else:
            correct |= {o.offer_id for o in sold if o.cabin.value == "ECONOMY" and o.fare_cents == floor}
    return correct, granted
