"""What a booking request must give, shared byte for byte by the booking_requirements tool
(src/plugin/guide.py) and the verifier (verifier/guide.py): every field of the booking task's input, read
from the contract, with an example; the date and time rules; and the airports. No policy: applying the
policy is the agent's job, not the traveller's. It imports only modules a verifier may use, contract, and its
package's shared modules.
"""

import dataclasses
import enum
import typing

from contract import AirportCode, AirportHelp, FieldHelp, RequirementsOutput, Topic, TripInput

from .rules import BOOKING_HORIZON_DAYS, date_of, day_number
from .world import AIRPORTS

EXAMPLE_DEPARTURE_DAYS = 30  # the example request travels this many days after today


def example_date(today):
    return date_of(day_number(today) + EXAMPLE_DEPARTURE_DAYS)


def examples(today):
    return {
        "traveller_name": "Jordan Lee",
        "origin": "DFW",
        "destination": "NRT",
        "travel_date": example_date(today),
        "preferred_departure": "11:00",
        "stop_preference": "NONSTOP",
        "wants_business": "true",
        "manager_approved_business": "true",
    }


def kind_of(name, kind):
    """What kind of value a field takes, in words."""
    if kind is bool:
        return "yes or no (true or false)"
    if isinstance(kind, type) and issubclass(kind, AirportCode):
        return f"an airport code from the airport list ({len(AIRPORTS)} airports)"
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return "one of " + ", ".join(member.value for member in kind)
    if name.endswith("_date"):
        return "a date, YYYY-MM-DD"
    if name == "preferred_departure":
        return "a time, HH:MM (24-hour clock)"
    return "text"


def fields(today):
    """Every field of the booking task's input, in the contract's order."""
    hints = typing.get_type_hints(TripInput, include_extras=True)
    example = examples(today)
    found = []
    for field in dataclasses.fields(TripInput):
        kind, description = typing.get_args(hints[field.name])
        found.append(FieldHelp(name=field.name, kind=kind_of(field.name, kind), required=True,
                               example=example[field.name], description=description))
    return found


def date_rules(today):
    last = date_of(day_number(today) + BOOKING_HORIZON_DAYS)
    return [
        f"Today is {today} (UTC): a request made today is booked as of today.",
        "The travel date is YYYY-MM-DD, the day the flight leaves, as a date where it leaves from.",
        (
            "The preferred departure is HH:MM on a 24-hour clock, local time where the flight leaves from; flights "
            "leave between 06:00 and 22:00 local time."
        ),
        (
            "Say NONSTOP or CONNECTING: the flight of that kind leaving closest to the preferred time is taken as "
            "the traveller's original flight (the earlier when two are as close)."
        ),
        f"Flights are sold from today up to {BOOKING_HORIZON_DAYS} days ahead: the travel date is {today} to {last}.",
    ]


def airports():
    return [AirportHelp(code=row[0], name=row[1], city=row[2], country=row[3]) for row in AIRPORTS]


def example_request(today):
    return (
        f"Book a flight for Jordan Lee from Dallas-Fort Worth (DFW) to Tokyo Narita (NRT) on {example_date(today)}, "
        "a nonstop leaving around 11:00, with business class requested and pre-approved by their AT&T manager."
    )


def build(topic, today):
    """The requirements for ``topic`` as of ``today``."""
    wants_fields = topic in (Topic.ALL, Topic.FIELDS)
    wants_airports = topic in (Topic.ALL, Topic.AIRPORTS)
    return RequirementsOutput(
        today=today,
        fields=fields(today) if wants_fields else [],
        date_rules=date_rules(today) if wants_fields else [],
        airports=airports() if wants_airports else [],
        example_request=example_request(today),
    )
