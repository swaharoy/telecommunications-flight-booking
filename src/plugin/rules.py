"""AT&T's air-travel rules for vendors, shared byte for byte by the tools (src/plugin/rules.py) and the
verifier (verifier/rules.py): dates and times, what a trip request may be, the original flight, which
itineraries are logical, the booking the policy requires, and the canonical form of requests and offers both
sides compare.

Exact integer arithmetic only, and no datetime (a verifier may not import it): a date is a day number and a
time a minute number. It imports only modules a verifier may use, and contract.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from contract import Cabin, StopPreference

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})$")
CLOCK = re.compile(r"^(\d{2}):(\d{2})$")
WINDOW_MINUTES = 120  # T1: an alternate flight departs and arrives within 2 hours of the original
EXTRA_STOPS = 1  # T1: a routing may add one interim stop
BUSINESS_SEGMENT_MINUTES = 480  # T3: business needs one flight of 8 continuous hours or more in the air
BOOKING_HORIZON_DAYS = 330  # flights are sold up to this many days after today
NAME_MOST_CHARS = 80


def day_number(date):
    """Days since 1970-01-01 of a YYYY-MM-DD date; ValueError when it is not a real date."""
    match = DATE.fullmatch(date)
    if not match:
        raise ValueError(f"{date!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"{date!r} is not a real date")
    year -= month <= 2
    era = year // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def date_of(number):
    """The YYYY-MM-DD date of a day number."""
    number += 719468
    era = number // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    shifted = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * shifted + 2) // 5 + 1
    month = shifted + (3 if shifted < 10 else -9)
    year = year_of_era + era * 400 + (month <= 2)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def is_date(text):
    try:
        day_number(text)
    except ValueError:
        return False
    return True


def minute_number(time):
    """Minutes since 1970-01-01 00:00 of a YYYY-MM-DD HH:MM time; ValueError when it is not one."""
    match = TIME.fullmatch(time)
    if not match:
        raise ValueError(f"{time!r} is not a YYYY-MM-DD HH:MM time")
    date, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{time!r} is not a real time")
    return day_number(date) * 1440 + hour * 60 + minute


def clock_minutes(text):
    """Minutes after midnight of an HH:MM clock time; ValueError when it is not one."""
    match = CLOCK.fullmatch(text)
    if not match:
        raise ValueError(f"{text!r} is not an HH:MM time")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"{text!r} is not a real time")
    return hour * 60 + minute


def is_clock(text):
    try:
        clock_minutes(text)
    except ValueError:
        return False
    return True


def request_problem(request):
    """What is wrong with a trip request on its own (no clock or flights needed), or None."""
    if not request.traveller_name.strip():
        return "traveller_name is blank: give the traveller's name"
    if len(request.traveller_name) > NAME_MOST_CHARS:
        return f"traveller_name is longer than {NAME_MOST_CHARS} characters"
    if request.origin is request.destination:
        return f"origin and destination are both {request.origin.value}: give two different airports"
    if not is_date(request.travel_date):
        return f"travel_date {request.travel_date!r} is not a real YYYY-MM-DD date"
    if not is_clock(request.preferred_departure):
        return f"preferred_departure {request.preferred_departure!r} is not an HH:MM time (00:00 to 23:59)"
    return None


def booking_date_problem(travel_date, booking_date):
    """What is wrong with travelling on ``travel_date`` booked on ``booking_date`` (today), or None."""
    if day_number(travel_date) < day_number(booking_date):
        return f"travel_date {travel_date} is before today, {booking_date}: flights cannot leave in the past"
    if day_number(travel_date) > day_number(booking_date) + BOOKING_HORIZON_DAYS:
        return (f"travel_date {travel_date} is more than {BOOKING_HORIZON_DAYS} days after today, {booking_date}: "
                "flights are not sold that far ahead")
    return None


def request_plain(request):
    """A trip request as plain JSON values, the form receipts record and the verifier compares."""
    return {
        "traveller_name": request.traveller_name,
        "origin": request.origin.value,
        "destination": request.destination.value,
        "travel_date": request.travel_date,
        "preferred_departure": request.preferred_departure,
        "stop_preference": request.stop_preference.value,
        "wants_business": request.wants_business,
        "manager_approved_business": request.manager_approved_business,
    }


def trip_matches_request(trip, request):
    """Whether a trip states exactly what the request asked for (its original flight is checked apart)."""
    return (
        trip.traveller_name == request.traveller_name
        and trip.origin.code == request.origin.value
        and trip.destination.code == request.destination.value
        and trip.travel_date == request.travel_date
        and trip.preferred_departure == request.preferred_departure
        and trip.stop_preference is request.stop_preference
        and trip.wants_business is request.wants_business
        and trip.manager_approved_business is request.manager_approved_business
    )


def stops_match(stops, preference):
    """NONSTOP is 0 stops; CONNECTING is one or more."""
    return stops == 0 if preference is StopPreference.NONSTOP else stops >= 1


def choose_original(itineraries, preference, preferred_departure):
    """The original flight: of the day's itineraries with the stated kind of stops, the one leaving closest to
    the preferred local time, the earlier when two are as close; None when no itinerary of that kind flies."""
    wanted = clock_minutes(preferred_departure)
    fitting = [itinerary for itinerary in itineraries if stops_match(itinerary.stops, preference)]
    if not fitting:
        return None
    return min(
        fitting,
        key=lambda i: (abs(clock_minutes(i.depart_local) - wanted), minute_number(i.depart), i.itinerary_id),
    )


def logical(original, offer):
    """T1: departs and arrives within 2 hours of the original's departure and arrival (exactly 120 minutes is
    fine), with at most one more interim stop than the original."""
    return (
        abs(minute_number(offer.depart) - minute_number(original.depart)) <= WINDOW_MINUTES
        and abs(minute_number(offer.arrive) - minute_number(original.arrive)) <= WINDOW_MINUTES
        and offer.stops <= original.stops + EXTRA_STOPS
    )


def long_segment(offer):
    """T3: whether one flight of the itinerary is in the air 480 minutes or more (added-up flights do not count)."""
    return any(segment.air_minutes >= BUSINESS_SEGMENT_MINUTES for segment in offer.segments)


def business_eligible(trip, offer):
    """T3, the traveller's side: business wanted and pre-approved, and the itinerary has an 8-hour flight."""
    return trip.wants_business and trip.manager_approved_business and long_segment(offer)


@dataclass
class Answer:
    """The booking the rules require for a trip and its offers."""

    logical: list  # itinerary ids within 2 hours and one extra stop of the original
    lowest_economy_fare_cents: int
    cheapest: list  # logical itinerary ids selling economy at that lowest fare
    correct: list  # offer ids that are correct bookings
    granted: list  # the correct offer ids booked with business granted


def solve(trip, offers):
    """T4 never first; T1 logical itineraries; T2 the lowest economy fare among them, refundable or not; T3
    business on that same itinerary when wanted, pre-approved, flown with an 8-hour flight and sold in business.
    Raises when no logical itinerary sells economy (the original's economy fare is always on sale)."""
    logical_offers = [offer for offer in offers if logical(trip.original, offer)]
    economy = [offer for offer in logical_offers if offer.cabin is Cabin.ECONOMY]
    if not economy:
        raise ValueError("no logical itinerary sells an economy fare: the original's economy fare is missing")
    lowest = min(offer.fare_cents for offer in economy)
    cheapest = sorted({offer.itinerary_id for offer in economy if offer.fare_cents == lowest})
    correct, granted = [], []
    for itinerary_id in cheapest:
        sold = [offer for offer in logical_offers if offer.itinerary_id == itinerary_id]
        business = [offer for offer in sold if offer.cabin is Cabin.BUSINESS]
        if business and business_eligible(trip, business[0]):
            least = min(offer.fare_cents for offer in business)
            chosen = [offer.offer_id for offer in business if offer.fare_cents == least]
            correct.extend(chosen)
            granted.extend(chosen)
        else:
            correct.extend(o.offer_id for o in sold if o.cabin is Cabin.ECONOMY and o.fare_cents == lowest)
    order = {offer.offer_id: index for index, offer in enumerate(offers)}
    return Answer(
        sorted({offer.itinerary_id for offer in logical_offers}),
        lowest,
        cheapest,
        sorted(correct, key=order.get),
        sorted(granted, key=order.get),
    )


def segment_plain(segment):
    return {
        "origin": segment.origin,
        "destination": segment.destination,
        "flight_number": segment.flight_number,
        "depart": segment.depart,
        "arrive": segment.arrive,
        "air_minutes": segment.air_minutes,
    }


def itinerary_plain(itinerary):
    """An itinerary as plain JSON values, the form both sides compare."""
    return {
        "itinerary_id": itinerary.itinerary_id,
        "carrier": itinerary.carrier,
        "stops": itinerary.stops,
        "depart": itinerary.depart,
        "arrive": itinerary.arrive,
        "depart_local": itinerary.depart_local,
        "segments": [segment_plain(segment) for segment in itinerary.segments],
    }


def offer_plain(offer):
    """An offer as plain JSON values, the form both sides hash."""
    return {
        "offer_id": offer.offer_id,
        "itinerary_id": offer.itinerary_id,
        "carrier": offer.carrier,
        "cabin": offer.cabin.value,
        "refundable": offer.refundable,
        "fare_cents": offer.fare_cents,
        "stops": offer.stops,
        "depart": offer.depart,
        "arrive": offer.arrive,
        "segments": [segment_plain(segment) for segment in offer.segments],
    }


def offers_digest(offers):
    """The SHA-256 of a list of offers in their canonical JSON form."""
    text = json.dumps([offer_plain(offer) for offer in offers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_offers(left, right):
    """Whether two lists of offers are the same offers, in the same order."""
    return [offer_plain(offer) for offer in left] == [offer_plain(offer) for offer in right]
