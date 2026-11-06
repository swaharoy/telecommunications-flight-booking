"""search_flights' checks: a well-formed query, and exactly the simulated world's offers for it."""

from .checks import RUN_ID, result
from .rules import is_date, same_offers
from .world import NOTE, offers_on


def verify_input(value):
    if value.origin is value.destination:
        return result(False, f"origin and destination are both {value.origin.value}")
    if not is_date(value.travel_date):
        return result(False, f"travel_date {value.travel_date!r} is not a real YYYY-MM-DD date")
    if value.run_id and not RUN_ID.fullmatch(value.run_id):
        return result(False, f"run_id {value.run_id!r} is not one get_trip returned")
    return result(True, "a well-formed search")


def verify_output(input_value, output_value, workspace):
    q = input_value
    if output_value.run_id != q.run_id:
        return result(False, "the result names another run")
    if output_value.note != NOTE:
        return result(False, "the result does not say its fares and schedules are simulated")
    expected = offers_on(q.origin.value, q.destination.value, q.travel_date)
    if not same_offers(output_value.offers, expected):
        return result(False, "the offers are not the route's offers on the searched day")
    return result(True, f"{len(expected)} offers on {q.origin.value}-{q.destination.value}, {q.travel_date}")
