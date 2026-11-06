"""solve_booking's checks: the pinned trip is the request's with its original flight, its offers are the
simulated world's, and its answer is what the rules give for them."""

from .checks import result
from .rules import same_offers, solve
from .trip import input_problem, trip_problem
from .world import offers_on


def verify_input(value):
    problem = input_problem(value)
    return result(problem is None, problem or "a well-formed trip request with an original flight")


def verify_output(input_value, output_value, workspace):
    problem = answer_key_problem(input_value, output_value)
    return result(problem is None, problem or "the answer key follows the rules")


def answer_key_problem(request, key):
    """What is wrong with a pinned answer key for ``request``, or None."""
    trip = key.trip
    problem = trip_problem(trip, request)
    if problem:
        return f"the answer key's trip: {problem}"
    if not key.pinned_at.startswith(trip.booking_date + " "):
        return "the answer key's booking date is not the day it was pinned"
    if not same_offers(key.offers, offers_on(trip.origin.code, trip.destination.code, trip.travel_date)):
        return "the answer key's offers are not the route's offers on the travel day"
    answer = solve(trip, key.offers)
    pinned = (key.logical_itinerary_ids, key.lowest_economy_fare_cents, key.cheapest_itinerary_ids,
              key.correct_offer_ids, key.granted_offer_ids)
    computed = (answer.logical, answer.lowest_economy_fare_cents, answer.cheapest, answer.correct, answer.granted)
    if pinned != computed:
        return "the answer key's booking is not what the rules give for its trip and offers"
    return None
