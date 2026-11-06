"""The telecommunications-flight-booking verdict: named checks, in order, on the answer key, the run the
submission names, its search receipts, and the booking against rules T1-T4.

Every search receipt is checked against the simulated world rebuilt here (verifier/world.py, the tools' own
file), so any offer the agent saw, on any day it searched, is known exactly.

The first five checks are integrity gates; the rest are the policy. The verdict is valid, scoring 1, only when
every check holds; any failure, gate or policy, scores 0: a booking follows the policy or it does not. A check
that depends on a failed one is "not checked". Expected values come from the verifier's own copy of the rules
applied to the pinned trip and offers; the answer key's own booking is checked to agree with them.
"""

from contract import Cabin

from .checks import check, result, run_files
from .rules import (
    BUSINESS_SEGMENT_MINUTES,
    EXTRA_STOPS,
    WINDOW_MINUTES,
    business_eligible,
    logical,
    long_segment,
    minute_number,
    offers_digest,
    request_plain,
    solve,
)
from .solve import answer_key_problem
from .world import offers_on

TEXT = {
    "answer-key": "The answer key pinned this request's trip, booked today with its original flight, its offers, "
                  "and a booking that follows the rules",
    "this-run": "The submission names a run get_trip began for this request on the same booking date, after the "
                "answer key",
    "searched": "The agent searched for flights in this run",
    "receipts-match": "Every search in this run returned exactly the route's offers for its query",
    "offer-seen": "The booked offer was among this run's search results, on the trip's route",
    "first": "T4: never first class",
    "logical": "T1: within 2 hours of the original's departure and arrival, with at most one extra stop",
    "lowest-coach": "T2: the itinerary with the lowest economy fare among the logical ones, at that fare when coach",
    "cabin": "T3: business on that itinerary only when wanted, pre-approved, flown with an 8-hour flight and sold",
    "business-granted": "T3: business_granted says whether business is granted",
}
GATES = ("answer-key", "this-run", "searched", "receipts-match", "offer-seen")
POLICY = ("first", "logical", "lowest-coach", "cabin", "business-granted")


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


class Verdict:
    def __init__(self):
        self.entries = {}
        self.blocked_by = None

    def add(self, check_id, ok, expected="", actual="", message=""):
        if self.blocked_by is not None:
            self.entries[check_id] = check(
                check_id, TEXT[check_id], None, message=f"not checked: {self.blocked_by} failed"
            )
            return
        self.entries[check_id] = check(check_id, TEXT[check_id], ok, expected, actual, message)
        if not ok:
            self.blocked_by = check_id

    def finish(self):
        entries = [self.entries[check_id] for check_id in GATES + POLICY]
        failed = [entry for entry in entries if entry["ok"] is False]
        if not failed:
            return result(True, "valid: the booking follows every rule", score=1.0, checks=entries)
        first = failed[0]
        return result(False, f"{first['id']}: {first['message']}", score=0.0, checks=entries)


def gates(verdict, arguments, output, reference, workspace):
    """The integrity gates; returns the offers this run's searches returned, by id."""
    problem = "no answer key was pinned" if reference is None else answer_key_problem(arguments, reference)
    route = f"{arguments.origin.value}-{arguments.destination.value} {arguments.travel_date}"
    verdict.add("answer-key", problem is None, f"the key of {route}",
                "none" if reference is None else f"booked {reference.trip.booking_date}",
                problem or "the answer key is this request's and follows the rules")
    if problem is not None:
        return {}
    trip = reference.trip

    started, searches = run_files(workspace, output.run_id)
    if not isinstance(started, dict) or started.get("request") != request_plain(arguments):
        verdict.add("this-run", False, "a run of this request", output.run_id,
                    f"the workspace holds no run {output.run_id!r} begun by get_trip for this request")
    elif started.get("booking_date") != trip.booking_date or started.get("original") != trip.original.itinerary_id:
        verdict.add("this-run", False, f"booked {trip.booking_date}, original {trip.original.itinerary_id}",
                    f"booked {started.get('booking_date')}, original {started.get('original')}",
                    f"run {output.run_id} was booked on another day, or from another original flight, than the "
                    "answer key")
    elif not isinstance(started.get("started_at"), str) or started["started_at"] < reference.pinned_at:
        verdict.add("this-run", False, f"begun after {reference.pinned_at}", str(started.get("started_at")),
                    f"run {output.run_id} began before this task's answer key: it is an earlier run")
    else:
        verdict.add("this-run", True, actual=output.run_id,
                    message=f"run {output.run_id} began at {started['started_at']}")

    verdict.add("searched", bool(searches), "at least one search_flights call", f"{len(searches)} searches",
                "searched" if searches else "the agent booked without calling search_flights in this run")

    seen = {}
    mismatch = None
    for number, receipt in enumerate(searches, start=1):
        if not isinstance(receipt, dict):
            mismatch = f"search {number}'s receipt is unreadable"
            break
        try:
            expected = offers_on(receipt["origin"], receipt["destination"], receipt["travel_date"])
        except (KeyError, TypeError, ValueError):
            mismatch = f"search {number}'s receipt is malformed"
            break
        if receipt.get("offer_ids") != [o.offer_id for o in expected] or receipt.get("digest") != offers_digest(expected):
            mismatch = f"search {number} returned offers other than the route's offers for its query"
            break
        seen.update({o.offer_id: o for o in expected})
    verdict.add("receipts-match", mismatch is None, "receipts equal to the route's offers", mismatch or "equal",
                mismatch or f"{len(searches)} search receipts match the simulated offers")

    route = f"{trip.origin.code}-{trip.destination.code}"
    if output.offer_id not in seen:
        verdict.add("offer-seen", False, "an offer id from this run's search results", output.offer_id,
                    f"offer {output.offer_id!r} was not among this run's search results")
    else:
        flown = seen[output.offer_id]
        flies = f"{flown.segments[0].origin}-{flown.segments[-1].destination}"
        verdict.add("offer-seen", flies == route, f"an offer on {route}", f"{output.offer_id} on {flies}",
                    f"offer {output.offer_id} was in the search results" if flies == route else
                    f"offer {output.offer_id} flies {flies}, not the trip's route {route}")
    return seen


def verify_task(arguments, output, reference, workspace):
    verdict = Verdict()
    seen = gates(verdict, arguments, output, reference, workspace)
    if verdict.blocked_by is not None:
        return unchecked(verdict)
    trip, offers = reference.trip, reference.offers
    answer = solve(trip, offers)
    offer = seen[output.offer_id]
    oid, original = offer.offer_id, trip.original

    # T4
    verdict.add("first", offer.cabin is not Cabin.FIRST, "ECONOMY or BUSINESS", offer.cabin.value,
                f"offer {oid} is first class, which is never reimbursed" if offer.cabin is Cabin.FIRST else
                f"offer {oid} is {offer.cabin.value.lower()}")
    if verdict.blocked_by is not None:
        return unchecked(verdict)
    # T1
    depart_gap = minute_number(offer.depart) - minute_number(original.depart)
    arrive_gap = minute_number(offer.arrive) - minute_number(original.arrive)
    expected = (f"departs {original.depart} and arrives {original.arrive}, each ±{WINDOW_MINUTES} min; "
                f"at most {original.stops + EXTRA_STOPS} stops")
    actual = f"departs {offer.depart} ({depart_gap:+d} min), arrives {offer.arrive} ({arrive_gap:+d} min), {offer.stops} stops"
    if logical(original, offer):
        message = f"itinerary {offer.itinerary_id} is a logical alternative to the original {original.itinerary_id}"
    elif offer.stops > original.stops + EXTRA_STOPS:
        message = (f"itinerary {offer.itinerary_id} makes {offer.stops} stops: more than one more than the original's "
                   f"{original.stops}")
    else:
        message = (f"itinerary {offer.itinerary_id} departs {depart_gap:+d} min and arrives {arrive_gap:+d} min from "
                   f"the original {original.itinerary_id}: more than {WINDOW_MINUTES} min")
    verdict.add("logical", logical(original, offer), expected, actual, message)
    if verdict.blocked_by is not None:
        return unchecked(verdict)
    # T2
    cheapest = ", ".join(answer.cheapest)
    if offer.itinerary_id not in answer.cheapest:
        fare = min(o.fare_cents for o in offers if o.itinerary_id == offer.itinerary_id and o.cabin is Cabin.ECONOMY)
        verdict.add("lowest-coach", False, f"itinerary {cheapest} at {money(answer.lowest_economy_fare_cents)}",
                    f"itinerary {offer.itinerary_id} at {money(fare)}",
                    f"itinerary {offer.itinerary_id}'s lowest economy fare is {money(fare)}; the lowest logical "
                    f"economy fare is {money(answer.lowest_economy_fare_cents)}, on {cheapest}")
    elif offer.cabin is Cabin.ECONOMY and offer.fare_cents != answer.lowest_economy_fare_cents:
        verdict.add("lowest-coach", False, money(answer.lowest_economy_fare_cents), money(offer.fare_cents),
                    f"offer {oid} is a {'refundable ' if offer.refundable else ''}economy fare of "
                    f"{money(offer.fare_cents)} on the right itinerary; its lowest economy fare is "
                    f"{money(answer.lowest_economy_fare_cents)}, refundable or not")
    else:
        verdict.add("lowest-coach", True, f"itinerary {cheapest}", f"itinerary {offer.itinerary_id}",
                    f"itinerary {offer.itinerary_id} has the lowest logical economy fare, "
                    f"{money(answer.lowest_economy_fare_cents)}")
    # T3 cabin
    business = [o for o in offers if o.itinerary_id == offer.itinerary_id and o.cabin is Cabin.BUSINESS]
    due = bool(business) and business_eligible(trip, offer)
    want = "BUSINESS" if due else "ECONOMY"
    if offer.cabin.value != want:
        verdict.add("cabin", False, want, offer.cabin.value, business_reason(trip, offer, bool(business), due))
    elif due and offer.fare_cents != min(o.fare_cents for o in business):
        verdict.add("cabin", False, money(min(o.fare_cents for o in business)), money(offer.fare_cents),
                    f"offer {oid} is not the itinerary's lowest business fare")
    else:
        verdict.add("cabin", True, want, offer.cabin.value, business_reason(trip, offer, bool(business), due))
    # T3 flag
    verdict.add("business-granted", output.business_granted is due, due, output.business_granted,
                f"business is {'granted' if due else 'not granted'} for offer {oid}; the submission says "
                f"{output.business_granted}")
    return verdict.finish()


def unchecked(verdict):
    """The verdict with every check after the failed one marked "not checked"."""
    for check_id in GATES + POLICY:
        if check_id not in verdict.entries:
            verdict.add(check_id, None)
    return verdict.finish()


def business_reason(trip, offer, sold, due):
    if due:
        return f"business is wanted, pre-approved and offered, and itinerary {offer.itinerary_id} has an 8-hour flight"
    if not trip.wants_business:
        return "the traveller did not ask for business: coach"
    if not trip.manager_approved_business:
        return "business was not pre-approved by the traveller's manager: coach"
    if not long_segment(offer):
        longest = max(segment.air_minutes for segment in offer.segments)
        return (f"itinerary {offer.itinerary_id}'s longest flight is {longest} min in the air: business needs one "
                f"flight of {BUSINESS_SEGMENT_MINUTES} min or more (flights are not added up)")
    if not sold:
        return f"itinerary {offer.itinerary_id} is not sold in business: coach"
    return "coach"
