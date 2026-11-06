"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON). Real simulated offers where they show the case, and
hand-built flights (in the tools and the verifier alike) for exact boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import (
    Run,
    booking,
    failed,
    hand_built,
    itinerary,
    judge,
    key_for,
    request,
    requests,
    sell,
    tool_input,
)
from slimconfig import build_output, plain_output

import verifier
from contract import (
    AirportCode,
    Itinerary,
    RequirementsInput,
    RequirementsOutput,
    SearchInput,
    SearchOutput,
    SolveOutput,
    Topic,
    TripOutput,
)
from plugin import booking_requirements
from plugin.rules import logical


def valid(verdict: dict) -> bool:
    return verdict["valid"] is True and verdict["score"] == 1.0


def refused(verdict: dict, *check_ids: str) -> bool:
    return verdict["valid"] is False and verdict["score"] == 0.0 and failed(verdict) == list(check_ids)


# Correct --------------------------------------------------------------------------------------------


def test_the_gold_booking_is_valid_for_varied_requests(tmp_path: Path) -> None:
    for index, value in enumerate(requests(60, "gold")):
        run = Run(value, tmp_path / str(index))
        verdict = run.judge(run.gold())
        assert valid(verdict), (plain_output(value), verdict["message"])
        assert all(entry["ok"] is True for entry in verdict["details"]["checks"])


def test_exactly_the_correct_offers_pass(tmp_path: Path) -> None:
    """Every offer the agent could book from its search is judged, with business_granted both ways: valid if
    and only if the answer key lists it as correct with that flag."""
    judged = 0
    for index, value in enumerate(requests(60, "every-offer")):
        run = Run(value, tmp_path / str(index))
        for found in run.offers:
            for granted in (False, True):
                verdict = run.judge(booking(run.run_id, found.offer_id, granted))
                right = found.offer_id in run.key.correct_offer_ids and granted is (
                    found.offer_id in run.key.granted_offer_ids)
                assert verdict["valid"] is right, (index, found.offer_id, granted, verdict["message"])
                judged += 1
    assert judged > 1_500


# Wrong, on real simulated offers -----------------------------------------------------------------------


def first_request(test, salt: str):
    """The first varied request whose answer key passes ``test(key)``."""
    for value in requests(3_000, salt):
        if test(key_for(value)):
            return value
    raise LookupError(salt)


def wrong(run: Run, pick, check_id: str, granted: bool = False) -> dict:
    chosen = next(o for o in run.offers if pick(o, run.key))
    verdict = run.judge(booking(run.run_id, chosen.offer_id, granted))
    assert refused(verdict, check_id), verdict["message"]
    return verdict


def test_first_class_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: any(o.cabin.value == "FIRST" for o in k.offers), "first")
    verdict = wrong(Run(value, tmp_path), lambda o, k: o.cabin.value == "FIRST", "first")
    assert "never" in verdict["message"]


def test_an_itinerary_too_far_from_the_original_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: any(o.itinerary_id not in k.logical_itinerary_ids and o.cabin.value == "ECONOMY"
                                        for o in k.offers), "far")
    verdict = wrong(Run(value, tmp_path), lambda o, k: o.itinerary_id not in k.logical_itinerary_ids
                    and o.cabin.value == "ECONOMY", "logical")
    assert "original" in verdict["message"]


def test_a_dearer_logical_itinerary_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: any(o.itinerary_id in k.logical_itinerary_ids and o.itinerary_id not in
                                        k.cheapest_itinerary_ids and o.cabin.value == "ECONOMY" for o in k.offers),
                          "dearer")
    verdict = wrong(Run(value, tmp_path), lambda o, k: o.itinerary_id in k.logical_itinerary_ids
                    and o.itinerary_id not in k.cheapest_itinerary_ids and o.cabin.value == "ECONOMY", "lowest-coach")
    assert "lowest logical economy fare" in verdict["message"]


def test_the_original_when_a_logical_alternative_is_cheaper_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.trip.original.itinerary_id not in k.cheapest_itinerary_ids, "original")
    wrong(Run(value, tmp_path), lambda o, k: o.itinerary_id == k.trip.original.itinerary_id
          and o.cabin.value == "ECONOMY" and not o.refundable, "lowest-coach")


def test_the_refundable_fare_on_the_right_itinerary_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: not k.granted_offer_ids and any(
        o.itinerary_id in k.cheapest_itinerary_ids and o.cabin.value == "ECONOMY" and o.refundable
        for o in k.offers), "refundable")
    verdict = wrong(Run(value, tmp_path), lambda o, k: o.itinerary_id in k.cheapest_itinerary_ids
                    and o.cabin.value == "ECONOMY" and o.refundable, "lowest-coach")
    assert "refundable" in verdict["message"]


def test_business_without_approval_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.trip.wants_business and not k.trip.manager_approved_business and any(
        o.itinerary_id in k.cheapest_itinerary_ids and o.cabin.value == "BUSINESS" for o in k.offers), "unapproved")
    verdict = wrong(Run(value, tmp_path), lambda o, k: o.itinerary_id in k.cheapest_itinerary_ids
                    and o.cabin.value == "BUSINESS", "cabin", granted=True)
    assert "pre-approved" in verdict["message"]


def test_coach_when_business_is_granted_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: bool(k.granted_offer_ids), "granted")
    run = Run(value, tmp_path)
    wrong(run, lambda o, k: o.itinerary_id in k.cheapest_itinerary_ids and o.cabin.value == "ECONOMY"
          and o.fare_cents == k.lowest_economy_fare_cents, "cabin")


def test_a_wrong_business_granted_flag_is_refused(tmp_path: Path) -> None:
    for salt, granted in (("flag-true", True), ("flag-false", False)):
        value = first_request(lambda k, g=granted: bool(k.granted_offer_ids) is g, salt)
        run = Run(value, tmp_path / salt)
        verdict = run.judge(run.gold() | {"business_granted": not granted})
        assert refused(verdict, "business-granted"), verdict["message"]


def test_an_offer_of_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    later = run.search("2026-12-04").offers[0]
    assert refused(run.judge(booking(run.run_id, later.offer_id)), "logical")


def test_an_offer_on_another_route_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    elsewhere = run.search(origin="IAH").offers[0]
    verdict = run.judge(booking(run.run_id, elsewhere.offer_id))
    assert refused(verdict, "offer-seen") and "not the trip's route" in verdict["message"]


# Exact boundaries, on hand-built flights -----------------------------------------------------------------

DAY = "2026-12-03"


def boundary(tmp_path: Path, itineraries: list[dict], offers: list[dict], value, offer_id: str,
             granted: bool = False) -> dict:
    with hand_built({DAY: {"itineraries": itineraries, "offers": offers}}):
        run = Run(value, tmp_path)
        return run.judge(booking(run.run_id, offer_id, granted))


@pytest.mark.parametrize(("shift", "ok"), [(120, True), (-120, True), (121, False), (-121, False)])
def test_an_alternative_exactly_two_hours_away_is_logical(tmp_path: Path, shift: int, ok: bool) -> None:
    original = itinerary(1, "17:00")  # 11:00 at DFW
    hours, minutes = divmod(17 * 60 + shift, 60)
    other = itinerary(2, f"{hours:02d}:{minutes:02d}")
    offers = [sell(original, 1, 90_000), sell(other, 2, 70_000)]
    verdict = boundary(tmp_path, [original, other], offers, request(), "20261203-02")
    assert valid(verdict) if ok else refused(verdict, "logical")


@pytest.mark.parametrize(("legs", "ok"), [((350, 260), True), ((200, 160, 160), False)])
def test_one_extra_stop_is_logical_and_two_are_not(tmp_path: Path, legs: tuple, ok: bool) -> None:
    original = itinerary(1, "17:00")  # nonstop, 700 minutes
    other = itinerary(2, "17:00", legs)  # lands within two hours of the original
    offers = [sell(original, 1, 90_000), sell(other, 2, 60_000)]
    assert logical(build_output(original, Itinerary), build_output(other, Itinerary)) is ok
    verdict = boundary(tmp_path, [original, other], offers, request(), "20261203-02")
    assert valid(verdict) if ok else refused(verdict, "logical")


@pytest.mark.parametrize(("minutes", "granted"), [((480,), True), ((479,), False), ((240, 240), False)])
def test_business_needs_one_flight_of_eight_hours(tmp_path: Path, minutes: tuple, granted: bool) -> None:
    original = itinerary(1, "17:00", minutes)
    offers = [sell(original, 1, 90_000), sell(original, 2, 400_000, cabin="BUSINESS")]
    value = request(wants_business=True, manager_approved_business=True,
                    stop_preference="NONSTOP" if len(minutes) == 1 else "CONNECTING")
    right, wrong_id = ("20261203-02", "20261203-01") if granted else ("20261203-01", "20261203-02")
    assert valid(boundary(tmp_path / "a", [original], offers, value, right, granted))
    assert refused(boundary(tmp_path / "b", [original], offers, value, wrong_id, not granted), "cabin")


def test_business_wanted_but_not_approved_is_coach(tmp_path: Path) -> None:
    original = itinerary(1, "17:00", (720,))
    offers = [sell(original, 1, 90_000), sell(original, 2, 400_000, cabin="BUSINESS")]
    value = request(wants_business=True, manager_approved_business=False)
    assert valid(boundary(tmp_path / "a", [original], offers, value, "20261203-01"))
    verdict = boundary(tmp_path / "b", [original], offers, value, "20261203-02", True)
    assert refused(verdict, "cabin") and "pre-approved" in verdict["message"]


def test_the_cheapest_fare_is_non_refundable_and_still_right(tmp_path: Path) -> None:
    original = itinerary(1, "17:00")
    offers = [sell(original, 1, 90_000), sell(original, 2, 160_000, refundable=True)]
    assert valid(boundary(tmp_path / "a", [original], offers, request(), "20261203-01"))
    assert refused(boundary(tmp_path / "b", [original], offers, request(), "20261203-02"), "lowest-coach")


def test_the_cheapest_fare_overall_in_first_class_or_far_away_is_refused(tmp_path: Path) -> None:
    original, far = itinerary(1, "17:00"), itinerary(2, "20:00")
    offers = [sell(original, 1, 90_000), sell(original, 2, 50_000, cabin="FIRST"), sell(far, 3, 40_000)]
    assert valid(boundary(tmp_path / "a", [original, far], offers, request(), "20261203-01"))
    assert refused(boundary(tmp_path / "b", [original, far], offers, request(), "20261203-02"), "first")
    assert refused(boundary(tmp_path / "c", [original, far], offers, request(), "20261203-03"), "logical")


def test_business_is_never_found_on_another_itinerary(tmp_path: Path) -> None:
    original, short = itinerary(1, "17:00", (700,)), itinerary(2, "17:30", (320, 300))
    offers = [sell(original, 1, 90_000), sell(original, 2, 400_000, cabin="BUSINESS"),
              sell(short, 3, 70_000), sell(short, 4, 300_000, cabin="BUSINESS")]
    value = request(wants_business=True, manager_approved_business=True)
    assert valid(boundary(tmp_path / "a", [original, short], offers, value, "20261203-03"))
    assert refused(boundary(tmp_path / "b", [original, short], offers, value, "20261203-02", True), "lowest-coach")
    assert refused(boundary(tmp_path / "c", [original, short], offers, value, "20261203-04", True), "cabin")


def test_no_flight_of_the_stated_kind_is_refused_before_booking(tmp_path: Path) -> None:
    original = itinerary(1, "17:00")
    with hand_built({DAY: {"itineraries": [original], "offers": [sell(original, 1, 90_000)]}}):
        check = verifier.verify_input("get_trip", request(stop_preference="CONNECTING"))
        assert check["valid"] is False and "no connecting flight" in check["message"]
        from plugin import get_trip

        with pytest.raises(ValueError, match="no connecting flight"):
            get_trip(request(stop_preference="CONNECTING"), tmp_path)


# Missing --------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(run.gold()), "searched")


@pytest.mark.parametrize("offer_id", ["20261203-99", "", "F01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, offer_id)), "offer-seen")


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(run.gold() | {"run_id": run_id}), "this-run")


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(run.request, run.gold(), None, run.workspace), "answer-key")


def test_an_answer_key_for_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(request(preferred_departure="19:00"), run.gold(), run.key, run.workspace), "answer-key")


# Tampering ------------------------------------------------------------------------------------------


def edit(path: Path, **changes) -> None:
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"origin": "XXX"},
                                     {"travel_date": "x"}, {"travel_date": "2026-12-04"}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "search-1.json", **changes)
    assert refused(run.judge(run.gold()), "receipts-match")


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", started_at="2026-11-05 00:00:00.000000")
    verdict = run.judge(run.gold())
    assert refused(verdict, "this-run") and "earlier run" in verdict["message"]


@pytest.mark.parametrize("changes", [{"booking_date": "2026-11-04"}, {"original": "20261203-I09"}])
def test_a_run_booked_another_day_or_from_another_original_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", **changes)
    assert refused(run.judge(run.gold()), "this-run")


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.correct_offer_ids = [o.offer_id for o in run.key.offers]
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_another_original_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.trip.original.depart_local = "05:00"
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_edited_offers_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.offers[0].fare_cents += 1
    assert refused(run.judge(run.gold()), "answer-key")


# Determinism and the tools' own checks -----------------------------------------------------------------


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(request(wants_business=True, manager_approved_business=True), tmp_path)
    for output in (run.gold(), booking(run.run_id, run.offers[0].offer_id, True)):
        assert json.dumps(run.judge(output), sort_keys=True) == json.dumps(run.judge(output), sort_keys=True)


def test_tool_inputs_are_checked() -> None:
    good = plain_output(request())
    assert tool_input("get_trip", good)["valid"] is True
    assert tool_input("solve_booking", good | {"stop_preference": "CONNECTING"})["valid"] is True
    for bad in ({"destination": "DFW"}, {"travel_date": "2026-02-30"}, {"preferred_departure": "7am"},
                {"preferred_departure": "24:00"}, {"traveller_name": " "}):
        assert tool_input("get_trip", good | bad)["valid"] is False, bad
        assert tool_input("solve_booking", good | bad)["valid"] is False, bad
    query = {"run_id": "", "origin": "JFK", "destination": "LAX", "travel_date": "2027-03-01"}
    assert tool_input("search_flights", query)["valid"] is True
    assert tool_input("search_flights", query | {"run_id": "0123456789ab"})["valid"] is True
    for bad in ({"travel_date": "2027-02-30"}, {"run_id": "nope"}, {"destination": "JFK"}):
        assert tool_input("search_flights", query | bad)["valid"] is False, bad
    for topic in Topic:
        assert tool_input("booking_requirements", {"topic": topic.value})["valid"] is True


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_output("get_trip", run.request, trip_out, str(run.workspace))["valid"] is True
    assert verifier.verify_output("get_trip", request(wants_business=True), trip_out,
                                  str(run.workspace))["valid"] is False
    other = build_output(plain_output(trip_out) | {"trip": plain_output(run.trip) | {
        "original": plain_output(run.trip.original) | {"depart_local": "21:00"}}}, TripOutput)
    assert verifier.verify_output("get_trip", run.request, other, str(run.workspace))["valid"] is False
    moved = build_output(plain_output(trip_out) | {"trip": plain_output(run.trip) | {"booking_date": "2026-12-04"}},
                         TripOutput)
    assert verifier.verify_output("get_trip", run.request, moved, str(run.workspace))["valid"] is False
    query = SearchInput(run.run_id, AirportCode.DFW, AirportCode.NRT, run.trip.travel_date)
    found = build_output(plain_output(SearchOutput(run.run_id, "Simulated fares and schedules; airline names are "
                                                   "used for realism only.", run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is True
    shifted = SearchInput(run.run_id, AirportCode.DFW, AirportCode.NRT, "2026-12-04")
    assert verifier.verify_output("search_flights", shifted, found, str(run.workspace))["valid"] is False
    found.offers[0].fare_cents -= 100
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    found.offers[0].fare_cents += 100
    found.note = "Real fares."
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    key = build_output(plain_output(run.key), SolveOutput)
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is True
    key.granted_offer_ids = key.correct_offer_ids
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("topic", list(Topic))
def test_the_requirements_are_checked(tmp_path: Path, topic: Topic) -> None:
    given = RequirementsInput(topic)
    made = build_output(plain_output(booking_requirements(given, tmp_path)), RequirementsOutput)
    assert verifier.verify_output("booking_requirements", given, made, str(tmp_path))["valid"] is True
    assert verifier.verify_task("booking-requirements", given, made, None, str(tmp_path))["valid"] is True
    for change in ({"today": "2026-13-01"}, {"example_request": "Book anything."},
                   {"airports": [] if topic is not Topic.FIELDS else [{"code": "BOS", "name": "x", "city": "y",
                                                                         "country": "US"}]}):
        altered = build_output(plain_output(made) | change, RequirementsOutput)
        assert verifier.verify_output("booking_requirements", given, altered, str(tmp_path))["valid"] is False, change


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    from plugin import search_flights

    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-01")
    found = build_output(plain_output(search_flights(query, tmp_path)), SearchOutput)
    assert verifier.verify_task("search-flights", query, found, None, str(tmp_path))["valid"] is True
    other = SearchInput("", AirportCode.JFK, AirportCode.SFO, "2026-12-01")
    assert verifier.verify_task("search-flights", other, found, None, str(tmp_path))["valid"] is False


def test_tools_refuse_past_and_far_dates(tmp_path: Path) -> None:
    from plugin import get_trip, search_flights

    with pytest.raises(ValueError, match="before today"):
        get_trip(request(travel_date="2026-11-04"), tmp_path)
    with pytest.raises(ValueError, match="330 days"):
        get_trip(request(travel_date="2027-10-02"), tmp_path)
    with pytest.raises(ValueError, match="before today"):
        search_flights(SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-11-01"), tmp_path)
    with pytest.raises(ValueError, match="get_trip first"):
        search_flights(SearchInput("0123456789ab", AirportCode.JFK, AirportCode.LAX, "2026-12-01"), tmp_path)
