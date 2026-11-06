"""get_trip: the trip a request describes, booked as of today, with its original flight, and a new run to book
it in."""

from pathlib import Path

from contract import Trip, TripInput, TripOutput
from plugin import receipts, world
from plugin.rules import booking_date_problem, choose_original, request_plain, request_problem


def original_problem(value: TripInput) -> str | None:
    """Why a request has no original flight (no flight of the stated kind flies that day), or None."""
    itineraries = world.itineraries_on(value.origin.value, value.destination.value, value.travel_date)
    if choose_original(itineraries, value.stop_preference, value.preferred_departure) is None:
        kind = "nonstop" if value.stop_preference.value == "NONSTOP" else "connecting"
        return (f"no {kind} flight flies {value.origin.value}-{value.destination.value} on {value.travel_date}: "
                "ask for the other kind of flight or another day")
    return None


def make_trip(value: TripInput, booking_date: str) -> Trip:
    """The trip of a request on ``booking_date``; raises when it cannot be booked that day."""
    problem = request_problem(value) or booking_date_problem(value.travel_date, booking_date) or original_problem(value)
    if problem:
        raise ValueError(problem)
    itineraries = world.itineraries_on(value.origin.value, value.destination.value, value.travel_date)
    return Trip(
        traveller_name=value.traveller_name,
        origin=world.airport(value.origin.value),
        destination=world.airport(value.destination.value),
        booking_date=booking_date,
        travel_date=value.travel_date,
        preferred_departure=value.preferred_departure,
        stop_preference=value.stop_preference,
        wants_business=value.wants_business,
        manager_approved_business=value.manager_approved_business,
        original=choose_original(itineraries, value.stop_preference, value.preferred_departure),
    )


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    run_id = receipts.new_run(workspace, request_plain(value), trip.booking_date, trip.original.itinerary_id, stamp)
    return TripOutput(run_id=run_id, trip=trip)
