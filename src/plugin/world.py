"""The simulated flight world, shared byte for byte by the tools (src/plugin/world.py) and the verifier
(verifier/world.py): real airports and real airline names, with synthetic schedules and fares.

The itineraries and offers on a route and travel day come from a SHA-256 stream keyed by the route and the
day only, so the same search gives the same offers on every machine, on any booking date, and the verifier
can rebuild any search the agent made. A route is flown several times a day, as real routes are, and each
itinerary is sold in several fares: a non-refundable economy fare always, often a refundable economy fare,
and business or first where the airline sells them. Nothing here is real fare or schedule data: airline names
are used for realism only. It imports only modules a verifier may use, contract, and the shared rules.
"""

import dataclasses
import hashlib
import math
from functools import cache

from contract import Airport, Cabin, Itinerary, Offer, Segment

from .rules import date_of, day_number

NOTE = "Simulated fares and schedules; airline names are used for realism only."

# Airports: OurAirports (https://ourairports.com/data/, public domain), fetched 2026-11-02, trimmed to 68
# large airports. The last column is the airport's standard-time UTC offset in minutes (no daylight
# saving), used only to keep departures in local daytime.
# (code, name, city, country, continent, latitude, longitude, UTC offset in minutes)
AIRPORTS = (
    ('ATL', 'Hartsfield Jackson Atlanta International Airport', 'Atlanta', 'US', 'NA', 33.6367, -84.4281, -300),
    ('LAX', 'Los Angeles International Airport', 'Los Angeles', 'US', 'NA', 33.9425, -118.408, -480),
    ('ORD', "Chicago O'Hare International Airport", 'Chicago', 'US', 'NA', 41.9786, -87.9048, -360),
    ('DFW', 'Dallas Fort Worth International Airport', 'Dallas-Fort Worth', 'US', 'NA', 32.8968, -97.038, -360),
    ('DEN', 'Denver International Airport', 'Denver', 'US', 'NA', 39.86, -104.6738, -420),
    ('JFK', 'John F. Kennedy International Airport', 'New York', 'US', 'NA', 40.6394, -73.7793, -300),
    ('SFO', 'San Francisco International Airport', 'San Francisco', 'US', 'NA', 37.6198, -122.3748, -480),
    ('SEA', 'Seattle–Tacoma International Airport', 'Seattle', 'US', 'NA', 47.4479, -122.3103, -480),
    ('LAS', 'Harry Reid International Airport', 'Las Vegas', 'US', 'NA', 36.0834, -115.1518, -480),
    ('MCO', 'Orlando International Airport', 'Orlando', 'US', 'NA', 28.4294, -81.309, -300),
    ('EWR', 'Newark Liberty International Airport', 'Newark', 'US', 'NA', 40.6894, -74.1705, -300),
    ('MIA', 'Miami International Airport', 'Miami', 'US', 'NA', 25.796, -80.2898, -300),
    ('CLT', 'Charlotte Douglas International Airport', 'Charlotte', 'US', 'NA', 35.214, -80.9431, -300),
    ('PHX', 'Phoenix Sky Harbor International Airport', 'Phoenix', 'US', 'NA', 33.4353, -112.0059, -420),
    ('IAH', 'George Bush Intercontinental Airport', 'Houston', 'US', 'NA', 29.9844, -95.3414, -360),
    ('BOS', 'Boston Logan International Airport', 'Boston', 'US', 'NA', 42.362, -71.0079, -300),
    ('MSP', 'Minneapolis–Saint Paul International Airport / Wold–Chamberlain Field', 'Minneapolis', 'US', 'NA', 44.8801, -93.2217, -360),
    ('DTW', 'Detroit Metropolitan Wayne County Airport', 'Detroit', 'US', 'NA', 42.2138, -83.3538, -300),
    ('PHL', 'Philadelphia International Airport', 'Philadelphia', 'US', 'NA', 39.8719, -75.2411, -300),
    ('LGA', 'LaGuardia Airport', 'New York', 'US', 'NA', 40.7772, -73.8726, -300),
    ('BWI', 'Baltimore/Washington International Thurgood Marshall Airport', 'Baltimore', 'US', 'NA', 39.1754, -76.6683, -300),
    ('SLC', 'Salt Lake City International Airport', 'Salt Lake City', 'US', 'NA', 40.7889, -111.9799, -420),
    ('SAN', 'San Diego International Airport', 'San Diego', 'US', 'NA', 32.7336, -117.19, -480),
    ('IAD', 'Washington Dulles International Airport', 'Dulles', 'US', 'NA', 38.9445, -77.4558, -300),
    ('DCA', 'Ronald Reagan Washington National Airport', 'Washington', 'US', 'NA', 38.8521, -77.0377, -300),
    ('TPA', 'Tampa International Airport', 'Tampa', 'US', 'NA', 27.9755, -82.5332, -300),
    ('AUS', 'Austin Bergstrom International Airport', 'Austin', 'US', 'NA', 30.1975, -97.662, -360),
    ('BNA', 'Nashville International Airport', 'Nashville', 'US', 'NA', 36.1245, -86.6782, -360),
    ('HNL', 'Daniel K. Inouye International Airport', 'Honolulu, Oahu', 'US', 'OC', 21.3184, -157.9257, -600),
    ('ANC', 'Ted Stevens Anchorage International Airport', 'Anchorage', 'US', 'NA', 61.179, -149.9926, -540),
    ('STL', 'St. Louis Lambert International Airport', 'St Louis', 'US', 'NA', 38.7487, -90.37, -360),
    ('YYZ', 'Toronto Pearson International Airport', 'Toronto', 'CA', 'NA', 43.6759, -79.6294, -300),
    ('YVR', 'Vancouver International Airport', 'Vancouver', 'CA', 'NA', 49.1939, -123.184, -480),
    ('YUL', 'Montreal / Pierre Elliott Trudeau International Airport', 'Montréal', 'CA', 'NA', 45.4678, -73.7423, -300),
    ('YHZ', 'Halifax / Stanfield International Airport', 'Halifax', 'CA', 'NA', 44.8808, -63.5086, -240),
    ('MEX', 'Mexico City Benito Juárez International Airport', 'Mexico City', 'MX', 'NA', 19.4358, -99.0703, -360),
    ('CUN', 'Cancún International Airport', 'Cancún', 'MX', 'NA', 21.0408, -86.8735, -300),
    ('LHR', 'London Heathrow Airport', 'London', 'GB', 'EU', 51.4707, -0.4599, 0),
    ('CDG', 'Charles de Gaulle International Airport', "Paris (Roissy-en-France, Val-d'Oise)", 'FR', 'EU', 49.009, 2.5541, 60),
    ('FRA', 'Frankfurt Main Airport', 'Frankfurt am Main', 'DE', 'EU', 50.0267, 8.5584, 60),
    ('AMS', 'Amsterdam Airport Schiphol', 'Amsterdam', 'NL', 'EU', 52.3086, 4.7639, 60),
    ('MAD', 'Adolfo Suárez Madrid–Barajas Airport', 'Madrid', 'ES', 'EU', 40.4934, -3.5722, 60),
    ('FCO', 'Rome–Fiumicino Leonardo da Vinci International Airport', 'Rome', 'IT', 'EU', 41.8045, 12.252, 60),
    ('MUC', 'Munich Airport', 'Munich', 'DE', 'EU', 48.3538, 11.7861, 60),
    ('ZRH', 'Zürich Airport', 'Zurich', 'CH', 'EU', 47.4581, 8.5481, 60),
    ('DUB', 'Dublin Airport', 'Dublin', 'IE', 'EU', 53.4287, -6.2621, 0),
    ('LIS', 'Lisbon Humberto Delgado Airport', 'Lisbon', 'PT', 'EU', 38.7813, -9.1359, 0),
    ('CPH', 'Copenhagen Kastrup Airport', 'Copenhagen', 'DK', 'EU', 55.6179, 12.656, 60),
    ('BCN', 'Josep Tarradellas Barcelona-El Prat Airport', 'Barcelona', 'ES', 'EU', 41.2971, 2.0785, 60),
    ('VIE', 'Vienna International Airport', 'Vienna', 'AT', 'EU', 48.1103, 16.5697, 60),
    ('BRU', 'Brussels Airport', 'Zaventem', 'BE', 'EU', 50.9014, 4.4844, 60),
    ('OSL', 'Oslo-Gardermoen International Airport', 'Oslo (Gardermoen)', 'NO', 'EU', 60.1939, 11.1004, 60),
    ('ARN', 'Stockholm-Arlanda Airport', 'Stockholm', 'SE', 'EU', 59.6485, 17.9288, 60),
    ('KEF', 'Keflavik International Airport', 'Reykjavík', 'IS', 'EU', 63.985, -22.6056, 0),
    ('MAN', 'Manchester Airport', 'Manchester, Greater Manchester', 'GB', 'EU', 53.3494, -2.2795, 0),
    ('EDI', 'Edinburgh Airport', 'Ingliston, Edinburgh', 'GB', 'EU', 55.9501, -3.3723, 0),
    ('SNN', 'Shannon Airport', 'Shannon', 'IE', 'EU', 52.702, -8.9248, 0),
    ('NRT', 'Narita International Airport', 'Narita', 'JP', 'AS', 35.7686, 140.3887, 540),
    ('ICN', 'Incheon International Airport', 'Seoul', 'KR', 'AS', 37.4691, 126.451, 540),
    ('SIN', 'Singapore Changi Airport', 'Singapore', 'SG', 'AS', 1.3502, 103.994, 480),
    ('HKG', 'Hong Kong International Airport', 'Hong Kong', 'HK', 'AS', 22.3118, 113.9149, 480),
    ('DXB', 'Dubai International Airport', 'Dubai', 'AE', 'AS', 25.2498, 55.371, 240),
    ('DEL', 'Indira Gandhi International Airport', 'New Delhi', 'IN', 'AS', 28.5556, 77.0952, 330),
    ('BOM', 'Chhatrapati Shivaji Maharaj International Airport', 'Mumbai', 'IN', 'AS', 19.0887, 72.8679, 330),
    ('SYD', 'Sydney Kingsford Smith International Airport', 'Sydney (Mascot)', 'AU', 'OC', -33.9461, 151.177, 600),
    ('GRU', 'São Paulo/Guarulhos–Governor André Franco Montoro International Airport', 'São Paulo', 'BR', 'SA', -23.4313, -46.47, -180),
    ('BOG', 'El Dorado International Airport', 'Bogota', 'CO', 'SA', 4.7016, -74.1469, -300),
    ('JNB', 'O.R. Tambo International Airport', 'Johannesburg', 'ZA', 'AF', -26.1401, 28.2468, 120),
)

# Airlines: (IATA code, name, country, kind, longest nonstop in km, hubs and focus airports among AIRPORTS,
# cabins sold). kind: "us" (U.S. network airline), "low" (low-cost or leisure), "intl" (other network
# airline). Cabins: Y economy, J business, F first (for a U.S. airline, domestic first only).
AIRLINES = (
    ("DL", "Delta Air Lines", "US", "us", 15500, ("ATL", "DTW", "MSP", "SLC", "JFK", "LAX", "SEA", "BOS"), "YJF"),
    ("UA", "United Airlines", "US", "us", 15500, ("ORD", "DEN", "IAH", "EWR", "SFO", "IAD", "LAX"), "YJF"),
    ("AA", "American Airlines", "US", "us", 15000, ("DFW", "CLT", "ORD", "MIA", "PHL", "PHX", "JFK", "LAX", "DCA"), "YJF"),
    ("AS", "Alaska Airlines", "US", "low", 11000, ("SEA", "ANC", "SFO", "LAX", "HNL"), "YJ"),
    ("B6", "JetBlue", "US", "low", 5800, ("JFK", "BOS", "MCO"), "YJ"),
    ("WN", "Southwest Airlines", "US", "low", 4200, ("LAS", "DEN", "BWI", "PHX", "AUS", "BNA", "STL", "MCO", "TPA"), "Y"),
    ("AC", "Air Canada", "CA", "intl", 15000, ("YYZ", "YVR", "YUL"), "YJ"),
    ("AM", "Aeromexico", "MX", "intl", 12500, ("MEX",), "YJ"),
    ("BA", "British Airways", "GB", "intl", 15000, ("LHR",), "YJF"),
    ("VS", "Virgin Atlantic", "GB", "intl", 13000, ("LHR", "MAN"), "YJ"),
    ("AF", "Air France", "FR", "intl", 15000, ("CDG",), "YJF"),
    ("KL", "KLM", "NL", "intl", 15000, ("AMS",), "YJ"),
    ("LH", "Lufthansa", "DE", "intl", 15000, ("FRA", "MUC"), "YJF"),
    ("LX", "Swiss", "CH", "intl", 14000, ("ZRH",), "YJF"),
    ("IB", "Iberia", "ES", "intl", 13000, ("MAD",), "YJ"),
    ("EI", "Aer Lingus", "IE", "intl", 8000, ("DUB",), "YJ"),
    ("TP", "TAP Air Portugal", "PT", "intl", 12000, ("LIS",), "YJ"),
    ("SK", "SAS", "DK", "intl", 11000, ("CPH", "OSL", "ARN"), "YJ"),
    ("FI", "Icelandair", "IS", "low", 7500, ("KEF",), "YJ"),
    ("EK", "Emirates", "AE", "intl", 16000, ("DXB",), "YJF"),
    ("NH", "ANA", "JP", "intl", 15000, ("NRT",), "YJF"),
    ("KE", "Korean Air", "KR", "intl", 15000, ("ICN",), "YJF"),
    ("SQ", "Singapore Airlines", "SG", "intl", 16500, ("SIN",), "YJF"),
    ("CX", "Cathay Pacific", "HK", "intl", 15000, ("HKG",), "YJF"),
    ("AI", "Air India", "IN", "intl", 15500, ("DEL", "BOM"), "YJF"),
    ("QF", "Qantas", "AU", "intl", 15500, ("SYD",), "YJF"),
    ("LA", "LATAM", "BR", "intl", 12500, ("GRU",), "YJ"),
    ("AV", "Avianca", "CO", "intl", 9500, ("BOG",), "YJ"),
    ("SA", "South African Airways", "ZA", "intl", 13000, ("JNB",), "YJ"),
)

# Synthetic schedule and fare model. Every constant is a modelling choice, not real data.
CRUISE_KMH = 870  # block speed: minutes in the air = TAXI_MINUTES + distance at this speed
TAXI_MINUTES = 20
FIRST_DEPARTURE = 6 * 60  # flights leave from 06:00 local time to the last before 22:00
LAST_DEPARTURE = 22 * 60
MIN_CONNECTION, MAX_CONNECTION = 45, 240  # minutes between flights at the hub (60 at least abroad)
MOST_ITINERARIES = 10  # itineraries flown on a route a day
MOST_NONSTOPS = 7
DETOUR = 1.35  # a connection flies at most this times the direct distance
SHORTEST_LEG_KM = 250
LONG_HAUL_KM = 2500
PEAK_HOURS = ((7 * 60, 10 * 60), (16 * 60, 20 * 60))  # local departures in these hours cost more


def fare_base(km):
    """A one-way economy fare in cents for a nonstop of ``km``: $50 plus a concave per-distance part."""
    return 5_000 + round(30 * km ** 0.85)


class Rng:
    """A pseudo-random stream built on SHA-256: the same numbers on every machine and Python version."""

    def __init__(self, label):
        self.prefix = f"telecommunications-flight-booking:{label}:"
        self.count = 0

    def bits(self):
        digest = hashlib.sha256(f"{self.prefix}{self.count}".encode()).digest()
        self.count += 1
        return int.from_bytes(digest[:8], "big")

    def randint(self, low, high):
        """An integer from low to high, both included."""
        if high < low:
            raise ValueError(f"empty range {low}..{high}")
        return low + self.bits() % (high - low + 1)

    def choice(self, items):
        if not items:
            raise ValueError("choice from an empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def chance(self, percent):
        return self.randint(1, 100) <= percent

    def shuffled(self, items):
        items = list(items)
        for index in range(len(items) - 1, 0, -1):
            other = self.randint(0, index)
            items[index], items[other] = items[other], items[index]
        return items


@cache
def airport_table():
    """{code: (code, name, city, country, continent, latitude, longitude, UTC offset)}"""
    return {row[0]: row for row in AIRPORTS}


@cache
def airline_table():
    return {row[0]: row for row in AIRLINES}


def is_airport(code):
    return code in airport_table()


def airport(code):
    row = airport_table().get(code)
    if row is None:
        raise ValueError(f"unknown airport {code!r}")
    return Airport(code=row[0], name=row[1], city=row[2], country=row[3], continent=row[4])


def country(code):
    return airport_table()[code][3]


def utc_offset(code):
    return airport_table()[code][7]


@cache
def distance_km(origin, destination):
    """Great-circle distance between two airports, in whole km."""
    a, b = airport_table()[origin], airport_table()[destination]
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (a[5], a[6], b[5], b[6]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(2 * 6371.0 * math.asin(math.sqrt(h)))


def air_minutes(origin, destination):
    """Minutes in the air for a nonstop flight: distance at block speed, plus taxi time."""
    return TAXI_MINUTES + round(distance_km(origin, destination) * 60 / CRUISE_KMH)


def leg_allowed(airline, origin, destination):
    """An airline may fly a leg within reach, and never one inside a country other than its own (cabotage)."""
    home, reach = airline[2], airline[4]
    if distance_km(origin, destination) > reach or distance_km(origin, destination) < SHORTEST_LEG_KM:
        return False
    return not (country(origin) == country(destination) != home)


@cache
def routings(origin, destination):
    """Every (airline code, airports flown through) an airline plausibly sells on a route: a nonstop when one
    end is its hub, and connections through its own hubs that add little distance."""
    direct = distance_km(origin, destination)
    found = []
    for airline in AIRLINES:
        code, hubs = airline[0], airline[5]
        if country(origin) == country(destination) != airline[2]:
            continue  # a domestic trip is sold by the country's own airlines only
        if (origin in hubs or destination in hubs) and leg_allowed(airline, origin, destination):
            found.append((code, (origin, destination)))
        if direct < 600:
            continue
        via = [
            hub for hub in hubs
            if hub not in (origin, destination)
            and leg_allowed(airline, origin, hub) and leg_allowed(airline, hub, destination)
            and distance_km(origin, hub) + distance_km(hub, destination) <= DETOUR * direct
        ]
        via.sort(key=lambda hub: (distance_km(origin, hub) + distance_km(hub, destination), hub))
        found.extend((code, (origin, hub, destination)) for hub in via[:2])
    return tuple(found)


def time_text(minute):
    """YYYY-MM-DD HH:MM of a minute number (minutes since 1970-01-01 00:00 UTC)."""
    return f"{date_of(minute // 1440)} {minute % 1440 // 60:02d}:{minute % 60:02d}"


def clock_text(minute):
    """HH:MM of a minute of the day."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def flight_number(code, origin, destination, frequency):
    """A stable flight number for an airline's leg and its n-th flight of the day, e.g. "DL 1482"."""
    digest = hashlib.sha256(f"flight:{code}:{origin}:{destination}:{frequency}".encode()).digest()
    return f"{code} {1 + int.from_bytes(digest[:4], 'big') % 2999}"


def is_long_haul(origin, destination):
    return distance_km(origin, destination) >= LONG_HAUL_KM


def frequencies(rng, path, direct):
    """How many times a day an airline flies a routing: shuttles often, long haul once or twice."""
    if len(path) == 3:
        return rng.randint(1, 2)
    if direct < 1_500:
        return rng.randint(2, 5)
    if direct < 4_500:
        return rng.randint(1, 4)
    return rng.randint(1, 2)


def build_segments(rng, airline_code, path, start, frequency):
    """The flights of an itinerary leaving at UTC minute ``start``, connecting 45-240 minutes later."""
    segments = []
    for index in range(len(path) - 1):
        a, b = path[index], path[index + 1]
        air = air_minutes(a, b)
        segments.append(Segment(
            origin=a, destination=b, flight_number=flight_number(airline_code, a, b, frequency),
            depart=time_text(start), arrive=time_text(start + air), air_minutes=air,
        ))
        low = 60 if country(a) != country(b) else MIN_CONNECTION
        start += air + rng.randint(low // 5, MAX_CONNECTION // 5) * 5
    return segments


def flights_of_day(origin, destination, day):
    """The day's flights before numbering: (UTC departure minute, local departure minute, airline code, path,
    frequency number), at most MOST_ITINERARIES, departing 06:00-21:55 local time on ``day`` at the origin."""
    rng = Rng(f"day:{origin}:{destination}:{day}")
    direct = distance_km(origin, destination)
    offset = utc_offset(origin)
    nonstops, connections = [], []
    for airline_code, path in routings(origin, destination):
        if not rng.chance(95 if len(path) == 2 else 75):
            continue
        times = set()
        for _ in range(frequencies(rng, path, direct)):
            times.add(rng.randint(FIRST_DEPARTURE // 5, LAST_DEPARTURE // 5 - 1) * 5)
        for number, local in enumerate(sorted(times), start=1):
            flight = (day * 1440 + local - offset, local, airline_code, path, number)
            (nonstops if len(path) == 2 else connections).append(flight)
    chosen = rng.shuffled(nonstops)[:MOST_NONSTOPS]
    chosen += rng.shuffled(connections)[: MOST_ITINERARIES - len(chosen)]
    return sorted(chosen, key=lambda f: (f[0], f[2], f[3], f[4]))


def peak(local):
    return any(low <= local < high for low, high in PEAK_HOURS)


def fares(rng, airline, path, local, origin, destination):
    """The fares an itinerary is sold at: [(cabin, refundable, fare in cents)], a non-refundable economy fare
    first and always."""
    direct = distance_km(origin, destination)
    kind, cabins = airline[3], airline[6]
    international = country(origin) != country(destination)
    long_haul = is_long_haul(origin, destination)
    economy = fare_base(direct) * rng.randint(80, 135) // 100
    if len(path) == 3:
        economy = economy * rng.randint(78, 95) // 100
    if kind == "low":
        economy = economy * 88 // 100
    if peak(local):
        economy = economy * rng.randint(108, 125) // 100
    sold = [(Cabin.ECONOMY, False, economy)]
    if rng.chance(65):
        sold.append((Cabin.ECONOMY, True, economy * rng.randint(150, 240) // 100))
    if "J" in cabins and (kind != "low" or long_haul):
        business = (international and (long_haul or kind == "intl")) or (direct >= 3_500 and rng.chance(60))
        if business and rng.chance(85):
            times = rng.randint(140, 190) if rng.chance(12) else rng.randint(300, 500)
            if not long_haul:
                times = rng.randint(180, 300)
            sold.append((Cabin.BUSINESS, rng.chance(50), economy * times // 100))
    if "F" in cabins and kind == "us" and not international and direct < 3_500 and rng.chance(70):
        sold.append((Cabin.FIRST, rng.chance(50), economy * rng.randint(180, 260) // 100))
    if "F" in cabins and long_haul and kind == "intl" and rng.chance(35):
        sold.append((Cabin.FIRST, True, economy * rng.randint(600, 900) // 100))
    return sold


@cache
def built_day(origin, destination, day):
    """(itineraries, offers) on a route leaving on day number ``day`` (the local date at the origin)."""
    if not is_airport(origin) or not is_airport(destination):
        raise ValueError(f"unknown route {origin!r} -> {destination!r}")
    if origin == destination:
        raise ValueError("origin and destination are the same airport")
    stamp = date_of(day).replace("-", "")
    itineraries, drafts = [], []
    for index, (start, local, airline_code, path, number) in enumerate(flights_of_day(origin, destination, day), 1):
        airline = airline_table()[airline_code]
        label = f"{origin}:{destination}:{day}:{airline_code}:{'-'.join(path)}:{number}"
        segments = build_segments(Rng(f"segments:{label}"), airline_code, path, start, number)
        itinerary = Itinerary(
            itinerary_id=f"{stamp}-I{index:02d}", carrier=airline[1], stops=len(segments) - 1,
            depart=segments[0].depart, arrive=segments[-1].arrive, depart_local=clock_text(local), segments=segments,
        )
        itineraries.append(itinerary)
        for rank, (cabin, refundable, fare) in enumerate(fares(Rng(f"fares:{label}"), airline, path, local, origin,
                                                               destination)):
            drafts.append((index, rank, itinerary, cabin, refundable, fare))
    offers = tuple(
        Offer(
            offer_id=f"{stamp}-{number:02d}", itinerary_id=itinerary.itinerary_id, carrier=itinerary.carrier,
            cabin=cabin, refundable=refundable, fare_cents=fare, stops=itinerary.stops, depart=itinerary.depart,
            arrive=itinerary.arrive, segments=itinerary.segments,
        )
        for number, (_, _, itinerary, cabin, refundable, fare) in enumerate(drafts, start=1)
    )
    return tuple(itineraries), offers


def copy_segments(segments):
    return [dataclasses.replace(segment) for segment in segments]


def day_itineraries(origin, destination, day):
    """The itineraries flown on a route on day number ``day``, in departure order. Fresh copies on each call."""
    return tuple(
        dataclasses.replace(itinerary, segments=copy_segments(itinerary.segments))
        for itinerary in built_day(origin, destination, day)[0]
    )


def day_offers(origin, destination, day):
    """Every offer on a route on day number ``day``, by departure, numbered <date>-01, ... Fresh copies on each
    call, so no caller can change another's offers."""
    return tuple(
        dataclasses.replace(offer, segments=copy_segments(offer.segments))
        for offer in built_day(origin, destination, day)[1]
    )


def itineraries_on(origin, destination, travel_date):
    return list(day_itineraries(origin, destination, day_number(travel_date)))


def offers_on(origin, destination, travel_date):
    return list(day_offers(origin, destination, day_number(travel_date)))
