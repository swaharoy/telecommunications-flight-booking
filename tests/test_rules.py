"""Rules T1-T4 and the original flight on hand-built trips and offers, every boundary included."""

from __future__ import annotations

import pytest
from helpers import request

from contract import Airport, Cabin, Itinerary, Offer, Segment, StopPreference, Trip
from plugin.rules import (
    booking_date_problem,
    choose_original,
    clock_minutes,
    date_of,
    day_number,
    logical,
    minute_number,
    request_problem,
    solve,
)
from plugin.world import time_text

DFW = Airport("DFW", "Dallas Fort Worth", "Dallas-Fort Worth", "US", "NA")
NRT = Airport("NRT", "Narita", "Narita", "JP", "AS")
DAY = "2027-03-20"


def itin(number, depart="12:00", minutes=(700,), *, local=None) -> Itinerary:
    start = minute_number(f"{DAY} {depart}")
    segments = []
    for index, air in enumerate(minutes):
        segments.append(Segment(f"P{index}", f"P{index + 1}", f"TA {number}{index}", time_text(start),
                                time_text(start + air), air))
        start += air + 90
    return Itinerary(f"20270320-I{number:02d}", "Test Air", len(minutes) - 1, segments[0].depart, segments[-1].arrive,
                     local or depart, segments)


def sell(itinerary, offer_id, fare, cabin=Cabin.ECONOMY, refundable=False) -> Offer:
    return Offer(offer_id, itinerary.itinerary_id, itinerary.carrier, cabin, refundable, fare, itinerary.stops,
                 itinerary.depart, itinerary.arrive, itinerary.segments)


def trip(original, *, business=False, approved=False) -> Trip:
    return Trip("Test Traveller", DFW, NRT, "2027-03-01", DAY, original.depart_local,
                StopPreference.NONSTOP if original.stops == 0 else StopPreference.CONNECTING, business, approved,
                original)


def test_dates_and_times_round_trip_and_reject_impossible_values() -> None:
    for text in ("1970-01-01", "2000-02-29", "2027-12-31", "2028-02-29", "2100-03-01"):
        assert date_of(day_number(text)) == text
    for bad in ("2027-02-29", "2027-13-01", "2027-1-01", "tomorrow"):
        with pytest.raises(ValueError):
            day_number(bad)
    assert minute_number("2027-01-02 00:00") - minute_number("2027-01-01 23:59") == 1
    assert clock_minutes("00:00") == 0 and clock_minutes("23:59") == 1439
    for bad in ("24:00", "9:00", "12:60", "noon"):
        with pytest.raises(ValueError):
            clock_minutes(bad)


def test_requests_are_checked_on_their_own() -> None:
    assert request_problem(request()) is None
    assert "both DFW" in request_problem(request(destination="DFW"))
    assert "not a real" in request_problem(request(travel_date="2026-02-30"))
    assert "HH:MM" in request_problem(request(preferred_departure="25:00"))
    assert "blank" in request_problem(request(traveller_name="  "))
    assert booking_date_problem("2026-11-05", "2026-11-05") is None
    assert "before today" in booking_date_problem("2026-11-04", "2026-11-05")
    assert booking_date_problem("2027-10-01", "2026-11-05") is None
    assert "330 days" in booking_date_problem("2027-10-02", "2026-11-05")


def test_the_original_is_the_stated_kind_closest_to_the_preferred_time() -> None:
    day = [itin(1, "08:00"), itin(2, "10:30"), itin(3, "11:00", (300, 300)), itin(4, "13:30")]
    assert choose_original(day, StopPreference.NONSTOP, "11:00").itinerary_id.endswith("I02")
    assert choose_original(day, StopPreference.CONNECTING, "06:00").itinerary_id.endswith("I03")
    assert choose_original(day, StopPreference.NONSTOP, "12:00").itinerary_id.endswith("I02"), "a tie takes the earlier"
    assert choose_original(day[:2], StopPreference.CONNECTING, "11:00") is None


@pytest.mark.parametrize(("shift", "ok"), [(120, True), (-120, True), (121, False), (-121, False)])
def test_two_hours_either_side_is_logical_and_a_minute_more_is_not(shift: int, ok: bool) -> None:
    original = itin(1, "12:00")
    moved = itin(2, time_text(minute_number(f"{DAY} 12:00") + shift)[11:])
    assert logical(original, moved) is ok
    later_arrival = itin(3, "12:00", (700 + shift,))
    assert logical(original, later_arrival) is ok


def test_one_extra_stop_is_logical_and_two_are_not() -> None:
    original = itin(1, "12:00", (700,))
    one = itin(2, "12:00", (300, 310))  # 300 + 90 connection + 310: lands with the original
    two = itin(3, "11:30", (250, 150, 130))  # two connections, within 30 minutes of the original both ends
    assert one.arrive == original.arrive and logical(original, one)
    assert abs(minute_number(two.arrive) - minute_number(original.arrive)) <= 120
    assert not logical(original, two)
    assert logical(itin(4, "12:00", (300, 310)), two), "connecting originals allow two stops"


def test_the_lowest_logical_coach_fare_wins_refundable_or_not() -> None:
    original, near, far = itin(1, "12:00"), itin(2, "13:30"), itin(3, "15:00")
    offers = [sell(original, "A", 90_000), sell(near, "B", 80_000, refundable=True), sell(near, "C", 120_000),
              sell(far, "D", 50_000)]
    answer = solve(trip(original), offers)
    assert answer.logical == [original.itinerary_id, near.itinerary_id]
    assert answer.correct == ["B"] and answer.lowest_economy_fare_cents == 80_000 and answer.granted == []


def test_first_class_is_never_booked_even_when_cheapest() -> None:
    original = itin(1, "12:00")
    offers = [sell(original, "A", 90_000), sell(original, "F", 40_000, Cabin.FIRST)]
    assert solve(trip(original), offers).correct == ["A"]


@pytest.mark.parametrize(("minutes", "granted"), [((480,), True), ((479,), False), ((240, 240), False),
                                                  ((480, 60), True)])
def test_business_needs_one_flight_of_480_minutes(minutes: tuple, granted: bool) -> None:
    original = itin(1, "12:00", minutes)
    offers = [sell(original, "E", 90_000), sell(original, "J", 400_000, Cabin.BUSINESS)]
    answer = solve(trip(original, business=True, approved=True), offers)
    assert answer.correct == (["J"] if granted else ["E"])
    assert answer.granted == (["J"] if granted else [])


@pytest.mark.parametrize(("wanted", "approved"), [(True, False), (False, True), (False, False)])
def test_business_needs_the_wish_and_the_approval(wanted: bool, approved: bool) -> None:
    original = itin(1, "12:00")
    offers = [sell(original, "E", 90_000), sell(original, "J", 400_000, Cabin.BUSINESS)]
    assert solve(trip(original, business=wanted, approved=approved), offers).correct == ["E"]


def test_business_stays_on_the_cheapest_itinerary() -> None:
    """The cheapest coach itinerary has no 8-hour flight; another logical one does: coach on the cheapest."""
    original, short = itin(1, "12:00", (700,)), itin(2, "12:30", (320, 320))
    offers = [sell(original, "E1", 90_000), sell(original, "J1", 400_000, Cabin.BUSINESS),
              sell(short, "E2", 70_000), sell(short, "J2", 300_000, Cabin.BUSINESS)]
    answer = solve(trip(original, business=True, approved=True), offers)
    assert answer.correct == ["E2"] and answer.granted == []


def test_business_needs_a_business_offer_on_that_itinerary() -> None:
    original = itin(1, "12:00")
    answer = solve(trip(original, business=True, approved=True), [sell(original, "E", 90_000)])
    assert answer.correct == ["E"] and answer.granted == []


def test_tied_coach_itineraries_are_both_correct() -> None:
    original, other = itin(1, "12:00"), itin(2, "12:05")
    answer = solve(trip(original), [sell(original, "A", 80_000), sell(other, "B", 80_000)])
    assert answer.correct == ["A", "B"] and answer.cheapest == [original.itinerary_id, other.itinerary_id]


def test_no_logical_economy_fare_raises() -> None:
    original = itin(1, "12:00")
    with pytest.raises(ValueError):
        solve(trip(original), [sell(original, "J", 400_000, Cabin.BUSINESS)])
