"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    BOOKING_REQUIREMENTS = "booking_requirements"
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    BOOKING_REQUIREMENTS = "booking-requirements"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "telecommunications-flight-booking"


class AirportCode(Enum):
    """The airports this plugin knows, by IATA code (booking_requirements lists their names and cities)."""

    ATL = "ATL"
    LAX = "LAX"
    ORD = "ORD"
    DFW = "DFW"
    DEN = "DEN"
    JFK = "JFK"
    SFO = "SFO"
    SEA = "SEA"
    LAS = "LAS"
    MCO = "MCO"
    EWR = "EWR"
    MIA = "MIA"
    CLT = "CLT"
    PHX = "PHX"
    IAH = "IAH"
    BOS = "BOS"
    MSP = "MSP"
    DTW = "DTW"
    PHL = "PHL"
    LGA = "LGA"
    BWI = "BWI"
    SLC = "SLC"
    SAN = "SAN"
    IAD = "IAD"
    DCA = "DCA"
    TPA = "TPA"
    AUS = "AUS"
    BNA = "BNA"
    HNL = "HNL"
    ANC = "ANC"
    STL = "STL"
    YYZ = "YYZ"
    YVR = "YVR"
    YUL = "YUL"
    YHZ = "YHZ"
    MEX = "MEX"
    CUN = "CUN"
    LHR = "LHR"
    CDG = "CDG"
    FRA = "FRA"
    AMS = "AMS"
    MAD = "MAD"
    FCO = "FCO"
    MUC = "MUC"
    ZRH = "ZRH"
    DUB = "DUB"
    LIS = "LIS"
    CPH = "CPH"
    BCN = "BCN"
    VIE = "VIE"
    BRU = "BRU"
    OSL = "OSL"
    ARN = "ARN"
    KEF = "KEF"
    MAN = "MAN"
    EDI = "EDI"
    SNN = "SNN"
    NRT = "NRT"
    ICN = "ICN"
    SIN = "SIN"
    HKG = "HKG"
    DXB = "DXB"
    DEL = "DEL"
    BOM = "BOM"
    SYD = "SYD"
    GRU = "GRU"
    BOG = "BOG"
    JNB = "JNB"


class StopPreference(Enum):
    NONSTOP = "NONSTOP"
    CONNECTING = "CONNECTING"


class Cabin(Enum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Topic(Enum):
    ALL = "ALL"
    FIELDS = "FIELDS"
    AIRPORTS = "AIRPORTS"


RUN_ID = "This booking run's id, as get_trip returned it"
TIME = "A UTC time, YYYY-MM-DD HH:MM"
CODE = "An IATA airport code, e.g. JFK"


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code, e.g. US"]
    continent: Annotated[str, "Its continent code: NA, SA, EU, AF, AS or OC"]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    flight_number: Annotated[str, "The airline's flight number, e.g. DL 1482"]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    air_minutes: Annotated[int, "Minutes in the air on this flight"]


@dataclass
class Itinerary(Output):
    itinerary_id: Annotated[str, "The itinerary's id: its departure date and number, e.g. 20261203-I04"]
    carrier: Annotated[str, "The airline"]
    stops: Annotated[int, "Interim stops: 0 for a nonstop, 1 for one connection"]
    depart: Annotated[str, "When the first flight leaves, UTC YYYY-MM-DD HH:MM"]
    arrive: Annotated[str, "When the last flight lands, UTC YYYY-MM-DD HH:MM"]
    depart_local: Annotated[str, "When the first flight leaves, HH:MM local time at the origin"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class Trip(Output):
    traveller_name: Annotated[str, "The traveller's name"]
    origin: Annotated[Airport, "The airport the trip leaves from"]
    destination: Annotated[Airport, "The airport the trip goes to"]
    booking_date: Annotated[str, "Today, the day the flight is booked, YYYY-MM-DD (UTC)"]
    travel_date: Annotated[str, "The day of travel, YYYY-MM-DD (local date at the origin)"]
    preferred_departure: Annotated[str, "The departure time the traveller asked for, HH:MM local time at the origin"]
    stop_preference: Annotated[StopPreference, "Whether the traveller asked for a nonstop or a connecting flight"]
    wants_business: Annotated[bool, "Whether the traveller asks for business class"]
    manager_approved_business: Annotated[bool, "Whether the traveller's AT&T manager pre-approved business class"]
    original: Annotated[
        Itinerary,
        "The original flight: the stated kind of flight that day leaving closest to the preferred time (the earlier "
        "when two are as close)",
    ]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id: its departure date and number, e.g. 20261203-07"]
    itinerary_id: Annotated[str, "The itinerary it sells; one itinerary is sold in several cabins and fares"]
    carrier: Annotated[str, "The airline"]
    cabin: Annotated[Cabin, "The cabin class"]
    refundable: Annotated[bool, "Whether the fare is refundable"]
    fare_cents: Annotated[int, "The fare, in US cents"]
    stops: Annotated[int, "Interim stops: 0 for a nonstop, 1 for one connection"]
    depart: Annotated[str, "When the first flight leaves, UTC YYYY-MM-DD HH:MM"]
    arrive: Annotated[str, "When the last flight lands, UTC YYYY-MM-DD HH:MM"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class TripInput(Output):
    traveller_name: Annotated[str, "The traveller's full name, as on the ticket"]
    origin: Annotated[AirportCode, "The airport to leave from, by IATA code (e.g. DFW for Dallas-Fort Worth)"]
    destination: Annotated[AirportCode, "The airport to fly to, by IATA code (e.g. NRT for Tokyo Narita)"]
    travel_date: Annotated[str, "The day to travel, YYYY-MM-DD, today or later"]
    preferred_departure: Annotated[str, "The time the traveller would like to leave, HH:MM local time at the origin"]
    stop_preference: Annotated[StopPreference, "NONSTOP for a direct flight, CONNECTING for a flight with a connection"]
    wants_business: Annotated[bool, "Whether the traveller asks for business class (the policy decides if it is granted)"]
    manager_approved_business: Annotated[bool, "Whether the traveller's AT&T manager pre-approved business class"]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The trip to book, with its original flight"]


@dataclass
class SearchInput(Output):
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[AirportCode, "The airport to leave from"]
    destination: Annotated[AirportCode, "The airport to fly to"]
    travel_date: Annotated[str, "The day to search, YYYY-MM-DD, today or later"]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    note: Annotated[str, "Where the offers come from: simulated fares and schedules"]
    offers: Annotated[list[Offer], "Every one-way offer on the route that day, by departure"]


@dataclass
class BookingOutput(Output):
    run_id: Annotated[str, RUN_ID]
    offer_id: Annotated[str, "The booked offer's id"]
    business_granted: Annotated[bool, "Whether business class is granted (and so booked)"]


@dataclass
class SolveOutput(Output):
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip, with today as its booking date and its original flight"]
    offers: Annotated[list[Offer], "Every offer on the route that day"]
    logical_itinerary_ids: Annotated[list[str], "The itineraries within 2 hours and one extra stop of the original"]
    lowest_economy_fare_cents: Annotated[int, "The lowest economy fare among the logical itineraries"]
    cheapest_itinerary_ids: Annotated[list[str], "The logical itineraries selling economy at that lowest fare"]
    correct_offer_ids: Annotated[list[str], "Every offer that is a correct booking"]
    granted_offer_ids: Annotated[list[str], "The correct offers booked with business granted"]


@dataclass
class RequirementsInput(Output):
    topic: Annotated[Topic, "ALL for everything, FIELDS for what to tell us, AIRPORTS for the airport list"]


@dataclass
class FieldHelp(Output):
    name: Annotated[str, "The field's name"]
    kind: Annotated[str, "What kind of value it takes"]
    required: Annotated[bool, "Whether every booking request must give it"]
    example: Annotated[str, "An example value"]
    description: Annotated[str, "What it means"]


@dataclass
class AirportHelp(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code"]


@dataclass
class RequirementsOutput(Output):
    today: Annotated[str, "Today, the booking date, YYYY-MM-DD (UTC)"]
    fields: Annotated[list[FieldHelp], "What a booking request gives, field by field; empty for AIRPORTS"]
    date_rules: Annotated[list[str], "How the travel date and time work; empty for AIRPORTS"]
    airports: Annotated[list[AirportHelp], "The airports a trip may use; empty for FIELDS"]
    example_request: Annotated[str, "A complete booking request in plain words"]


TOOLS = {
    Tool.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}
