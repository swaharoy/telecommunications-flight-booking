"""The simulated world: real airports and airlines flying plausible routes several times a day, synthetic but
realistic fares and schedules, the same on every machine, and an answer key that agrees with an independent
reading of the rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from helpers import CODES, requests
from oracle import booking_answer
from slimconfig import plain_output

from contract import AirportCode, SearchInput
from plugin import receipts, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, logical, minute_number

DAY = day_number("2026-12-03")
GOLDEN = {
    ("DFW", "NRT"): "72c9996ad00a7a22",
    ("JFK", "LAX"): "73b281c3dbcbeb2a",
    ("ATL", "ORD"): "b0684d608581f872",
    ("BOS", "LHR"): "cd08bf73570e3633",
    ("SFO", "SIN"): "6a21a8c61eb16e88",
    ("LHR", "CDG"): "ee58e9f05ce11a2d",
}
US_AIRLINES = {row[1] for row in world.AIRLINES if row[2] == "US"}
FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2} [1-9]\d{0,3}$")
LARGEST_SEARCH_CHARS = 40_000  # one day's search must stay well inside the hosted model's 65,536-token budget


def routes(step: int = 5):
    """Every ``step``-th route of all 68 x 67."""
    pairs = [(a, b) for a in CODES for b in CODES if a != b]
    return pairs[::step]


def digest(day) -> str:
    itineraries, offers = day
    text = json.dumps([[plain_output(i) for i in itineraries], [plain_output(o) for o in offers]], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("route", sorted(GOLDEN))
def test_a_route_and_day_make_the_same_flights_everywhere(route) -> None:
    assert digest(world.built_day(*route, DAY)) == GOLDEN[route]


def test_the_airports_are_the_contract_codes() -> None:
    assert [row[0] for row in world.AIRPORTS] == [member.value for member in AirportCode]
    assert len(world.AIRPORTS) == 68
    assert all(-720 <= row[7] <= 720 and row[7] % 30 == 0 for row in world.AIRPORTS)


def test_the_airlines_are_real_names_with_hubs_among_the_airports() -> None:
    assert "Delta Air Lines" in US_AIRLINES and "Japan Airlines" not in US_AIRLINES
    for code, _name, _country, kind, reach, hubs, cabins in world.AIRLINES:
        assert re.fullmatch(r"[A-Z0-9]{2}", code) and kind in ("us", "low", "intl") and reach > 0
        assert hubs and all(world.is_airport(hub) for hub in hubs), code
        assert cabins in ("Y", "YJ", "YJF")


def local_minute(time: str, code: str) -> int:
    return minute_number(time) + world.utc_offset(code)


def test_flights_are_well_formed_and_plausible() -> None:
    airline_of = {row[1]: row for row in world.AIRLINES}
    for origin, destination in routes():
        domestic = world.country(origin) == world.country(destination) == "US"
        for day in (DAY, DAY + 40):
            itineraries, offers = world.built_day(origin, destination, day)
            stamp = date_of(day).replace("-", "")
            assert [i.itinerary_id for i in itineraries] == [f"{stamp}-I{n:02d}" for n in range(1, len(itineraries) + 1)]
            assert [o.offer_id for o in offers] == [f"{stamp}-{n:02d}" for n in range(1, len(offers) + 1)]
            assert len(itineraries) <= world.MOST_ITINERARIES
            by_id = {i.itinerary_id: i for i in itineraries}
            for itinerary in itineraries:
                first, last = itinerary.segments[0], itinerary.segments[-1]
                local = local_minute(first.depart, origin)
                assert local // 1440 == day and 6 * 60 <= local % 1440 < 22 * 60, "leaves on the day, in daytime"
                assert itinerary.depart_local == world.clock_text(local % 1440)
                assert first.origin == origin and last.destination == destination
                assert (itinerary.depart, itinerary.arrive, itinerary.stops) == (first.depart, last.arrive,
                                                                              len(itinerary.segments) - 1)
                for one, two in zip(itinerary.segments, itinerary.segments[1:]):
                    assert one.destination == two.origin
                    assert 45 <= minute_number(two.depart) - minute_number(one.arrive) <= 240
                airline = airline_of[itinerary.carrier]
                if domestic:
                    assert itinerary.carrier in US_AIRLINES
                for segment in itinerary.segments:
                    assert FLIGHT_NUMBER.fullmatch(segment.flight_number)
                    assert segment.flight_number.startswith(airline[0] + " ")
                    inside = world.country(segment.origin) == world.country(segment.destination)
                    assert not inside or world.country(segment.origin) == airline[2], "no cabotage"
                if itinerary.stops:
                    assert itinerary.segments[0].destination in airline[5], "connects at the airline's hub"
                sold = [o for o in offers if o.itinerary_id == itinerary.itinerary_id]
                assert sold[0].cabin.value == "ECONOMY" and sold[0].refundable is False, "a saver fare always"
                assert sum(o.cabin.value == "BUSINESS" for o in sold) <= 1
                for offer in sold:
                    assert offer.fare_cents > 0 and offer.carrier == itinerary.carrier
                    assert (offer.depart, offer.arrive, offer.stops) == (itinerary.depart, itinerary.arrive,
                                                                        itinerary.stops)
                    assert [plain_output(s) for s in offer.segments] == [plain_output(s) for s in itinerary.segments]
                    if offer.cabin.value == "FIRST":
                        assert "F" in airline[6]
                    if offer.cabin.value == "ECONOMY" and offer.refundable:
                        assert offer.fare_cents > sold[0].fare_cents
            assert set(by_id) == {o.itinerary_id for o in offers}


def test_live_searches_hold_the_realistic_traps() -> None:
    """Across routes, the situations the policy is about turn up without being planted."""
    seen = set()
    for origin, destination in routes(3):
        itineraries, offers = world.built_day(origin, destination, DAY)
        saver = {o.itinerary_id: o.fare_cents for o in offers if o.cabin.value == "ECONOMY" and not o.refundable}
        for original in itineraries:
            near = [i for i in itineraries if i is not original and logical(original, i)]
            if any(saver[i.itinerary_id] < saver[original.itinerary_id] for i in near):
                seen.add("a cheaper logical alternative")
            if any(not logical(original, i) and saver[i.itinerary_id] < min([saver[original.itinerary_id]]
                   + [saver[n.itinerary_id] for n in near]) for i in itineraries):
                seen.add("a cheaper itinerary that is not logical")
        if any(o.cabin.value == "ECONOMY" and o.refundable for o in offers):
            seen.add("a refundable economy fare")
        if any(o.cabin.value == "FIRST" for o in offers):
            seen.add("first class")
        if any(o.cabin.value == "BUSINESS" and max(s.air_minutes for s in o.segments) >= 480 for o in offers):
            seen.add("business with an 8-hour flight")
        if any(o.cabin.value == "BUSINESS" and max(s.air_minutes for s in o.segments) < 480
               and sum(s.air_minutes for s in o.segments) >= 480 for o in offers):
            seen.add("business whose flights add up to 8 hours but none is")
        if any(i.stops == 0 for i in itineraries) and any(i.stops for i in itineraries):
            seen.add("nonstops and connections")
    assert seen == {"a cheaper logical alternative", "a cheaper itinerary that is not logical",
                    "a refundable economy fare", "first class", "business with an 8-hour flight",
                    "business whose flights add up to 8 hours but none is", "nonstops and connections"}


def test_searches_fit_the_hosted_context() -> None:
    largest = 0
    for origin, destination in routes(7):
        offers = world.day_offers(origin, destination, DAY)
        largest = max(largest, len(json.dumps([plain_output(offer) for offer in offers])))
    assert largest <= LARGEST_SEARCH_CHARS, largest


def test_offers_do_not_depend_on_the_booking_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-20")
    early = search_flights(query, tmp_path)
    monkeypatch.setattr(receipts, "CLOCK", lambda: "2026-12-19 08:00:00.000000")
    assert plain_output(search_flights(query, tmp_path)) == plain_output(early)


def test_unknown_or_equal_airports_are_refused() -> None:
    with pytest.raises(ValueError):
        world.day_offers("XXX", "LHR", DAY)
    with pytest.raises(ValueError):
        world.day_offers("BOS", "BOS", DAY)


def test_the_answer_key_agrees_with_an_independent_reading_for_400_requests(tmp_path: Path) -> None:
    outcomes = set()
    count = 0
    for value in requests(450, "oracle"):
        key = solve_booking(value, tmp_path)
        correct, granted = booking_answer(key.trip, key.offers)
        assert set(key.correct_offer_ids) == correct, plain_output(value)
        assert set(key.granted_offer_ids) == granted, plain_output(value)
        outcomes.add((bool(key.granted_offer_ids), key.trip.original.itinerary_id in key.cheapest_itinerary_ids))
        count += 1
    assert count >= 350
    assert outcomes == {(False, False), (False, True), (True, False), (True, True)}
