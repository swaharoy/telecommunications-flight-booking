# Telecommunications Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): a vendor describes a trip in plain words, including when they
would like to leave and whether they want a nonstop, an agent books one one-way flight for it under a
telecommunications company's vendor air-travel policy, as of today, and a deterministic verifier checks the
booking against every rule.

The policy is based on the **AT&T Vendor Expense Policy** (updated 11/20/19,
<https://globalsupplychain.att.com/downloads/Vendor-Expense-Policy.pdf>), section 3.4 *Air Travel
Arrangements* and the air items of section 1.1. This plugin is **unofficial**: it is not made, endorsed or
used by AT&T, and it restates the policy as exact rules of its own (below).

**Simulated fares and schedules.** Airports and airline names are real; every flight, fare and schedule is
synthetic, made by the plugin (see *The simulated flights* below). Airline names are used for realism only:
nothing here is a real fare or a real timetable.

## Tools

| Tool | Does | Code |
|---|---|---|
| `booking_requirements` | What a booking request must give, field by field with examples (read from the contract), the date and time rules, the airports to choose from, and an example request, as of today. Nothing about the policy: applying it is the agent's job | `src/plugin/requirements.py`, `src/plugin/guide.py` |
| `get_trip` | Begins a booking run for a trip request: the trip as booked today (traveller, airports with country and continent, booking date, travel date, preferred time, nonstop or connecting, business wish and approval), its **original flight**, and its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The one-way offers on a route on a day (today or later): every itinerary flown that day in every fare it is sold at, with airline, flight numbers, times, stops, minutes in the air, cabin, refundability and fare | `src/plugin/search.py` |
| `solve_booking` | The answer key: the trip as booked today, its offers and the booking the rules require. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `booking-requirements` | Shows what to tell us to book a flight (topic `ALL`, `FIELDS` or `AIRPORTS`) | `tool`, with `booking_requirements` |
| `search-flights` | Shows the offers on a route and day | `tool`, with `search_flights` |
| `telecommunications-flight-booking` | Books a flight for a trip request under the policy | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The booking task's input is the trip request, which the chat fills from plain words such as "book Jordan
Lee from Dallas to Tokyo Narita on Dec 3, a nonstop around 11am, business class, pre-approved by their
manager": `traveller_name`, `origin` and `destination` (airport codes from the list), `travel_date`,
`preferred_departure` (HH:MM, local time at the origin), `stop_preference` (`NONSTOP` or `CONNECTING`),
`wants_business` and `manager_approved_business`. The booking date is today (UTC), read when the answer key
is pinned; requests travelling before today or more than 330 days ahead are refused.

**The original flight.** The policy measures every alternative against the traveller's *original* flight.
The traveller does not name it: of the day's flights of the stated kind (nonstop, or with a connection),
the one leaving closest to the preferred time is the original, the earlier when two are as close. A
request is refused when no flight of that kind flies the route that day.

The agent's path is three tool calls: `get_trip` with the request, `search_flights` with the trip's route
and travel date, then `submit`. It submits `run_id`, `offer_id` and `business_granted`.

### The rules (the task's instructions state them exactly)

| Rule | Policy text it formalises (§3.4, §1.1) | Exact rule |
|---|---|---|
| T1 | "Vendors must consider … routing requiring one additional interim stop in each direction, or an alternate flight within 2 hours of the original departure and arrival time" | An itinerary is *logical* when it departs within 120 minutes of the original's departure and arrives within 120 minutes of its arrival (exactly 120 is fine), with at most one more stop than the original. Only logical itineraries may be booked |
| T2 | "Vendors must select lowest logical coach airfare … must consider non-refundable fares" | Book an itinerary with the lowest economy fare among the logical ones, refundable or not (any of them when tied), at that fare |
| T3 | "Vendors can request business class when a single segment of flight time ('in air time' excluding stops, layovers and ground time) is 8 continuous hours or more; providing the relevant manager pre-approves." | On that same itinerary, business is granted only if wanted, pre-approved, one of its flights is in the air 480 minutes or more (flights are never added up) and it is sold in business; then its lowest business fare is booked. Never move to another itinerary to get business |
| T4 | "First class bookings are not reimbursable" | Never a `FIRST` offer |

Out of scope: flight insurance, airline Wi-Fi, baggage beyond the first bag, upgrades and upgrade coupons,
prepaid air passes and airline clubs (§1.1); the "consider videoconferencing first" and pre-approval of travel
rules (§3.0, §3.1); the 50-mile no-travel rule (§3.16); and round trips ("in each direction": the policy adds
nothing for a return flight that a one-way booking does not test).

### The simulated flights

`src/plugin/world.py` (the same file as `verifier/world.py`) makes the itineraries and offers on a route and
day from a SHA-256 stream keyed by the route and the day only, so a search gives the same offers on every
machine and on any booking date, and the verifier rebuilds every search the agent made. Its model, every
constant of which is a modelling choice, not data:

- **Airports:** 68 large airports from OurAirports (public domain), fetched 2026-11-02, with their
  standard-time UTC offsets. Times are UTC; the travel date and the preferred time are local at the origin,
  and flights leave between 06:00 and 22:00 local time.
- **Airlines:** 29 real airlines, each with its country, hubs among the 68 airports, longest nonstop and
  cabins sold. An airline sells a nonstop when one end is its hub, and connections through its own hubs that
  add at most 35% distance; a domestic trip is sold only by that country's airlines, and no airline flies a
  leg inside another country.
- **Frequencies:** an airline flies a short nonstop 2-5 times a day, a medium one 1-4 times and a long-haul
  one 1-2 times, and a connection 1-2 times; up to 10 itineraries fly a route each day (up to 7 nonstop).
  Flight numbers (e.g. `DL 1482`) are stable per airline, leg and daily frequency.
- **Times:** minutes in the air are 20 + the great-circle distance at 870 km/h; connections take 45 to 240
  minutes (60 at least between countries).
- **Fares:** each itinerary is sold at a non-refundable economy fare, always: $50 + 30 x km^0.85 cents, times
  0.80-1.35 by day, connections 78-95% of that, low-cost airlines 88%, and 8-25% more for departures at 07-10
  or 16-20 local time. Often also a refundable economy fare at 1.5-2.4x; business at 3-5x on long haul
  (sometimes a 1.4-1.9x sale) and 1.8-3x on shorter flights, refundable or not; domestic first on U.S.
  airlines at 1.8-2.6x; long-haul first at 6-9x.

Exact boundaries (exactly 120 minutes from the original, two extra stops, a 480-minute flight against two
240-minute flights) rarely occur in realistic schedules, so the tests and scripted cases check them with
hand-built flights, which replace the world in the tools and the verifier alike.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and their instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py, IMPLEMENTATIONS) and the tools
│   ├── world.py     # airports, airlines and the simulated flights; the same file as verifier/world.py
│   ├── rules.py     # requests, the original flight and rules T1-T4 as exact integer code; the same file as verifier/rules.py
│   ├── guide.py     # what a booking request must give; the same file as verifier/guide.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, world, requirements, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the requirements, the offers table, the booking
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a
message naming the offer and the rule:

- integrity gates: `answer-key` (the pinned key is this request's, booked on the day it was pinned, with
  its original flight and the route's offers, and follows the rules), `this-run` (the submitted run was begun
  by `get_trip` for this request, on the same booking date and from the same original flight, after the key
  was pinned), `searched`, `receipts-match` (every search receipt equals the route's offers for its query,
  rebuilt by the verifier), `offer-seen` (the booked offer was in this run's search results, on the trip's
  route);
- policy: `first`, `logical`, `lowest-coach`, `cabin`, `business-granted`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0, since a booking
either follows the policy or it does not. Checks after a failed one are "not checked". Expected values come
from the verifier's own copy of the rules applied to the pinned trip and offers.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The tests freeze today at 2026-11-05, so they pass on any day. `uv run pytest` replays the scripted cases
in `tests/cases/` (gold, wrong, missing, malformed, tampered and boundary runs) through the real tools and
verifier, checks the answer key against an independent reading of the rules for 350+ varied requests, and
checks the simulated world's plausibility, determinism and size.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only
their receipts there, under `runs/`. To check the plugin with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```
