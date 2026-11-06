"""solve_booking, the reference tool: the trip booked as of today with its original flight, every offer that
day and the booking the rules require, pinned before the agent starts and never shown to it."""

from pathlib import Path

from contract import SolveOutput, TripInput
from plugin import receipts, world
from plugin.rules import solve
from plugin.trip import make_trip


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    offers = world.offers_on(trip.origin.code, trip.destination.code, trip.travel_date)
    answer = solve(trip, offers)
    return SolveOutput(
        pinned_at=stamp,
        trip=trip,
        offers=offers,
        logical_itinerary_ids=answer.logical,
        lowest_economy_fare_cents=answer.lowest_economy_fare_cents,
        cheapest_itinerary_ids=answer.cheapest,
        correct_offer_ids=answer.correct,
        granted_offer_ids=answer.granted,
    )
