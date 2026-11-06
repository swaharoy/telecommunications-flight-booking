"""get_trip's checks: a request that can be booked and has an original flight, the trip it states, its original
flight, and the run it began."""

from .checks import RUN_ID, read_json, result
from .rules import (
    booking_date_problem,
    choose_original,
    is_date,
    itinerary_plain,
    request_plain,
    request_problem,
    trip_matches_request,
)
from .world import airport, itineraries_on


def original_problem(value):
    """Why a well-formed request has no original flight, or None."""
    itineraries = itineraries_on(value.origin.value, value.destination.value, value.travel_date)
    if choose_original(itineraries, value.stop_preference, value.preferred_departure) is None:
        kind = "nonstop" if value.stop_preference.value == "NONSTOP" else "connecting"
        return (f"no {kind} flight flies {value.origin.value}-{value.destination.value} on {value.travel_date}: "
                "ask for the other kind of flight or another day")
    return None


def input_problem(value):
    return request_problem(value) or original_problem(value)


def verify_input(value):
    problem = input_problem(value)
    return result(problem is None, problem or "a well-formed trip request with an original flight")


def trip_problem(trip, request):
    """What is wrong with a trip stated for ``request`` (its booking date aside from the clock), or None."""
    if not trip_matches_request(trip, request):
        return "the trip is not the one the request asked for"
    if trip.origin != airport(trip.origin.code) or trip.destination != airport(trip.destination.code):
        return "the trip's airports are not the airport list's"
    if not is_date(trip.booking_date):
        return f"booking_date {trip.booking_date!r} is not a real YYYY-MM-DD date"
    problem = booking_date_problem(trip.travel_date, trip.booking_date)
    if problem:
        return problem
    itineraries = itineraries_on(trip.origin.code, trip.destination.code, trip.travel_date)
    original = choose_original(itineraries, trip.stop_preference, trip.preferred_departure)
    if original is None or itinerary_plain(trip.original) != itinerary_plain(original):
        return "the trip's original flight is not the one leaving closest to the preferred time"
    return None


def verify_output(input_value, output_value, workspace):
    trip = output_value.trip
    problem = trip_problem(trip, input_value)
    if problem:
        return result(False, problem)
    if not RUN_ID.fullmatch(output_value.run_id):
        return result(False, f"run_id {output_value.run_id!r} is not a run id")
    receipt = read_json(f"{workspace}/runs/{output_value.run_id}/trip.json")
    if (
        receipt is None
        or receipt.get("request") != request_plain(input_value)
        or receipt.get("booking_date") != trip.booking_date
        or receipt.get("original") != trip.original.itinerary_id
    ):
        return result(False, f"run {output_value.run_id} has no receipt for this request in the workspace")
    return result(True, f"the trip of the request, booked {trip.booking_date}, original flight "
                        f"{trip.original.itinerary_id}, run {output_value.run_id}")
