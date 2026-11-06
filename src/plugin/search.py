"""search_flights: the one-way offers on a route on the travel day, every itinerary in every fare it is sold at."""

from pathlib import Path

from contract import SearchInput, SearchOutput
from plugin import receipts, world
from plugin.rules import booking_date_problem, offers_digest


def search_flights(value: SearchInput, workspace: Path) -> SearchOutput:
    if value.origin is value.destination:
        raise ValueError("origin and destination are the same airport")
    # In a booking run, today is the run's booking date; a search outside a run (run_id empty) is only shown.
    folder, started = receipts.run_trip(workspace, value.run_id) if value.run_id else (None, None)
    today = started["booking_date"] if started else receipts.CLOCK()[:10]
    problem = booking_date_problem(value.travel_date, today)
    if problem:
        raise ValueError(problem)
    offers = world.offers_on(value.origin.value, value.destination.value, value.travel_date)
    if folder is not None:
        receipts.add_search(
            folder,
            {
                "origin": value.origin.value,
                "destination": value.destination.value,
                "travel_date": value.travel_date,
                "offer_ids": [offer.offer_id for offer in offers],
                "digest": offers_digest(offers),
            },
        )
    return SearchOutput(run_id=value.run_id, note=world.NOTE, offers=offers)
