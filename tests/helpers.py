"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
import verifier.world
from contract import TASKS, TOOLS, AirportCode, Itinerary, Offer, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number

BOOK = Task.BOOK_FLIGHT.value
CODES = [member.value for member in AirportCode]


def request(**changes) -> TripInput:
    """A trip request: by default a vendor flying DFW-NRT on 2026-12-03, a nonstop around 11:00, no business."""
    value = {
        "traveller_name": "Jordan Lee", "origin": "DFW", "destination": "NRT", "travel_date": "2026-12-03",
        "preferred_departure": "11:00", "stop_preference": "NONSTOP", "wants_business": False,
        "manager_approved_business": False,
    } | changes
    return build_output(value, TripInput)


def requests(count: int, salt: str = "requests"):
    """Up to ``count`` varied trip requests that have an original flight, chosen by SHA-256 so they are the same
    on every machine: any route, a day 0 to 60 days after today, any time, both kinds of flight, every
    combination of business wish and approval (long-haul routes favoured, so business comes up)."""
    long_haul = [(a, b) for a in CODES for b in CODES if a != b and world.distance_km(a, b) >= 7_000]
    for index in range(count):
        digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        if digest[0] % 2:
            origin, destination = long_haul[int.from_bytes(digest[1:3], "big") % len(long_haul)]
        else:
            origin, destination = CODES[digest[1] % len(CODES)], CODES[digest[2] % len(CODES)]
        if origin == destination:
            continue
        hour, minute = 6 + digest[3] % 16, digest[4] % 12 * 5
        value = request(origin=origin, destination=destination, travel_date=date_of(day_number("2026-11-05") + digest[5] % 60),
                        preferred_departure=f"{hour:02d}:{minute:02d}",
                        stop_preference="NONSTOP" if digest[6] % 3 else "CONNECTING",
                        wants_business=digest[7] % 4 != 0, manager_approved_business=digest[8] % 4 != 0)
        if verifier.verify_input("get_trip", value)["valid"]:
            yield value


def booking(run_id: str, offer_id: str, granted: bool = False) -> dict:
    return {"run_id": run_id, "offer_id": offer_id, "business_granted": granted}


def judge(arguments: TripInput, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output(plain_output(arguments), given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and a search in the workspace."""

    def __init__(self, value: TripInput, root: Path, *, search: bool = True) -> None:
        self.request = value
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(value, scratch)
        started = get_trip(value, self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, travel_date: str | None = None, *, origin=None, destination=None):
        trip = self.trip
        return search_flights(
            SearchInput(self.run_id, AirportCode(origin or trip.origin.code),
                        AirportCode(destination or trip.destination.code), travel_date or trip.travel_date),
            self.workspace,
        )

    def gold(self) -> dict:
        offer_id = self.key.correct_offer_ids[0]
        return booking(self.run_id, offer_id, offer_id in self.key.granted_offer_ids)

    def judge(self, output: dict) -> dict:
        return judge(self.request, output, self.key, self.workspace)


def key_for(value: TripInput):
    """The answer key of a request, pinned in a throwaway folder."""
    with tempfile.TemporaryDirectory() as folder:
        return solve_booking(value, Path(folder))


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def build_day(itineraries: list[dict], offers: list[dict]):
    return (tuple(build_output(i, Itinerary) for i in itineraries), tuple(build_output(o, Offer) for o in offers))


@contextmanager
def hand_built(world_value: dict, origin: str = "DFW", destination: str = "NRT"):
    """The world replaced, in the tools and the verifier alike, by hand-built itineraries and offers on one
    route: {date: {"itineraries": [...], "offers": [...]}}, and nothing on any other route or day. Used for exact
    boundaries real schedules rarely hit."""
    days = {day_number(date): build_day(value["itineraries"], value["offers"]) for date, value in world_value.items()}

    def built_day(o, d, day):
        return days.get(day, ((), ())) if (o, d) == (origin, destination) else ((), ())

    saved = world.built_day, verifier.world.built_day
    world.built_day = verifier.world.built_day = built_day
    try:
        yield
    finally:
        world.built_day, verifier.world.built_day = saved


def itinerary(number: int, depart: str, minutes: tuple = (700,), *, origin: str = "DFW", destination: str = "NRT",
              carrier: str = "American Airlines", local_offset: int = -360, date: str = "2026-12-03") -> dict:
    """A plain hand-built itinerary leaving at UTC ``depart`` (HH:MM on ``date``): a nonstop, or through hubs
    when ``minutes`` has more values, with 90-minute connections."""
    points = [origin, *["LAX", "HNL"][: len(minutes) - 1], destination]
    start = minute_number(f"{date} {depart}")
    segments = []
    for index, air in enumerate(minutes):
        segments.append({
            "origin": points[index], "destination": points[index + 1], "flight_number": f"AA {100 * number + index}",
            "depart": world.time_text(start), "arrive": world.time_text(start + air), "air_minutes": air,
        })
        start += air + 90
    local = (minute_number(segments[0]["depart"]) + local_offset) % 1440
    return {"itinerary_id": f"{date.replace('-', '')}-I{number:02d}", "carrier": carrier, "stops": len(minutes) - 1,
            "depart": segments[0]["depart"], "arrive": segments[-1]["arrive"], "depart_local": world.clock_text(local),
            "segments": segments}


def sell(itin: dict, number: int, fare: int, *, cabin: str = "ECONOMY", refundable: bool = False) -> dict:
    """A plain hand-built offer selling ``itin``."""
    stamp = itin["itinerary_id"][:8]
    return {"offer_id": f"{stamp}-{number:02d}", "itinerary_id": itin["itinerary_id"], "carrier": itin["carrier"],
            "cabin": cabin, "refundable": refundable, "fare_cents": fare, "stops": itin["stops"],
            "depart": itin["depart"], "arrive": itin["arrive"], "segments": itin["segments"]}
