"""Tool schemas — the text the model reads to decide when to call these tools."""

from __future__ import annotations

_ORIGIN = {
    "type": "object",
    "description": "A departure airport the traveller can reach.",
    "properties": {
        "city": {"type": "string", "description": "City of the airport, e.g. 'Bologna'."},
        "airports": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IATA codes, e.g. ['BLQ'].",
        },
        "access_cost": {
            "type": "number",
            "description": (
                "Cost per person to reach this airport and come back, in the chosen currency. "
                "Include train, bus, parking or fuel: this is the line that makes different "
                "airports honestly comparable."
            ),
        },
    },
    "required": ["city", "airports"],
}

_DESTINATION = {
    "type": "object",
    "description": "A candidate city to stay in.",
    "properties": {
        "city": {
            "type": "string",
            "description": "City name as a search engine expects it, e.g. 'Vienna'.",
        },
        "airports": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The city's airports, e.g. ['VIE'] or ['BUD'].",
        },
        "country": {
            "type": "string",
            "description": "ISO-2 country code, e.g. 'AT'. Needed for the food and attraction estimates.",
        },
        "transfer_cost": {
            "type": "number",
            "description": "Cost per person, each way, airport to city centre.",
        },
    },
    "required": ["city", "airports"],
}

_COMMON = {
    "adults": {"type": "integer", "description": "Adult travellers. Default 1."},
    "rooms": {"type": "integer", "description": "Hotel rooms. Default 1."},
    "currency": {"type": "string", "description": "Currency for every price. Default 'EUR'."},
    "language": {
        "type": "string",
        "description": "Language of the Google pages queried. Default 'it'.",
    },
    "max_requests": {
        "type": "integer",
        "description": (
            "Network request budget for this search. Default 80. If it runs out, the answer is "
            "partial and says so instead of pretending it finished."
        ),
    },
    "min_interval": {
        "type": "number",
        "description": (
            "Minimum seconds between two requests. Raise it if searches get blocked. Default 1.0."
        ),
    },
    "cache_ttl_hours": {
        "type": "number",
        "description": "How long a cached price stays valid, in hours. Default 12.",
    },
}

SEARCH = {
    "name": "tripscout_search",
    "description": (
        "Find the cheapest complete trip (flight + place to stay + getting to the airport) over "
        "a date window and several candidate cities, and rank whole trips by total cost. Use this "
        "when someone asks where and when to go cheaply and is flexible about the destination: it "
        "searches flights and lodging TOGETHER on the same dates, instead of pricing a flight and "
        "then discovering the hotel costs more on those nights. Prices a whole grid, caches every "
        "result in SQLite so a repeat search is nearly free, and prunes combinations whose lodging "
        "alone already breaks the budget. Returns a ranked list with the cost breakdown per option, "
        "so the answer is 'go here, these dates, this total', not a wall of flights."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origins": {
                "type": "array",
                "items": _ORIGIN,
                "description": "Departure airports considered; all of them are compared against each other.",
            },
            "destinations": {
                "type": "array",
                "items": _DESTINATION,
                "description": "Candidate cities. Keep it to 4-12: each one costs requests.",
            },
            "window_start": {
                "type": "string",
                "description": "Earliest departure date, YYYY-MM-DD. Omit to use the next weekends.",
            },
            "window_end": {
                "type": "string",
                "description": "Latest date by which the traveller must be back, YYYY-MM-DD.",
            },
            "weekends": {
                "type": "integer",
                "description": (
                    "When no dates are given: how many Thursday-to-Sunday weekends to explore from "
                    "today. Default 2."
                ),
            },
            "nights_min": {"type": "integer", "description": "Minimum nights. Default 2."},
            "nights_max": {"type": "integer", "description": "Maximum nights. Default 4."},
            "weekdays": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Allowed departure weekdays, English or Italian names: ['thursday','friday'] or "
                    "['giovedì','venerdì']. Default Thursday and Friday."
                ),
            },
            "budget_total": {
                "type": "number",
                "description": (
                    "Spending ceiling for the whole trip, for the group described. Combinations that "
                    "break it on the lodging alone are never priced on flights."
                ),
            },
            "top": {"type": "integer", "description": "How many options to return. Default 10."},
            "max_stops": {
                "type": "integer",
                "description": "Maximum stops per leg. 0 = nonstop only.",
            },
            "lodging": {
                "type": "array",
                "items": {"type": "string", "enum": ["hotel", "hostel", "apartment", "any"]},
                "description": (
                    "Which kinds of bed are acceptable: 'hostel' to spend little, 'apartment' for a "
                    "whole home or a private room, 'hotel' for hotels (capsule hotels and motels "
                    "included), 'any' for everything. Default 'any'. The category comes from "
                    "Google's own entity type (gcid), not from the property's name."
                ),
            },
            "estimates": {
                "type": "boolean",
                "description": (
                    "When true, adds to each option an approximate food and attraction cost for the "
                    "days on the ground, plus a second total that includes them. Estimates never "
                    "change the ranking, which stays on the bookable cost."
                ),
            },
            "food_per_day": {
                "type": "number",
                "description": "Food per person per day, to override the per-country table.",
            },
            "activities_per_day": {
                "type": "number",
                "description": "Tickets and attractions per person per day, to override the default.",
            },
            **_COMMON,
        },
        "required": ["origins", "destinations"],
    },
}

PRICE_TRIP = {
    "name": "tripscout_price_trip",
    "description": (
        "Price one exact trip end to end: the cheapest flight for those dates, the cheapest place "
        "to stay for the same nights, ground access to the departure airport and the transfer into "
        "town, with the total and every line of the breakdown. Use it to confirm or detail a single "
        "option that tripscout_search already surfaced, or when the user has already chosen a city "
        "and dates and wants to know what it really costs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin_airport": {"type": "string", "description": "Departure IATA, e.g. 'BLQ'."},
            "origin_city": {
                "type": "string",
                "description": "Departure city, for readability only.",
            },
            "access_cost": {
                "type": "number",
                "description": "Cost per person to reach the departure airport and come back.",
            },
            "dest_city": {"type": "string", "description": "Destination city, e.g. 'Vienna'."},
            "dest_airport": {"type": "string", "description": "Arrival IATA, e.g. 'VIE'."},
            "transfer_cost": {
                "type": "number",
                "description": "Cost per person, each way, airport to city centre.",
            },
            "depart": {"type": "string", "description": "Outbound date, YYYY-MM-DD."},
            "ret": {"type": "string", "description": "Return date, YYYY-MM-DD."},
            "max_stops": {"type": "integer", "description": "Maximum stops per leg."},
            "country": {
                "type": "string",
                "description": "ISO-2 country code (e.g. 'AT'): used by the food and attraction estimates.",
            },
            "lodging": {
                "type": "array",
                "items": {"type": "string", "enum": ["hotel", "hostel", "apartment", "any"]},
                "description": "Which kinds of bed are acceptable. Default 'any'.",
            },
            "estimates": {
                "type": "boolean",
                "description": "Add the food and attraction estimate and the total that includes them.",
            },
            "food_per_day": {
                "type": "number",
                "description": "Food per person per day, overridden.",
            },
            "activities_per_day": {
                "type": "number",
                "description": "Attractions per person per day, overridden.",
            },
            **_COMMON,
        },
        "required": ["origin_airport", "dest_city", "dest_airport", "depart", "ret"],
    },
}

HISTORY = {
    "name": "tripscout_history",
    "description": (
        "Show the price history tripscout has recorded for one route or one stay, plus the lowest "
        "price ever observed and what is currently cached. Use it to answer 'is this cheap for "
        "these dates?' or 'what did we see before?' without spending new requests. Reads only the "
        "local SQLite cache."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["flight", "hotel", "all"],
                "description": "What to look at. Default 'all' (a cache inventory).",
            },
            "origin_airport": {"type": "string", "description": "Departure IATA, for flights."},
            "dest_airport": {"type": "string", "description": "Arrival IATA, for flights."},
            "dest_city": {"type": "string", "description": "Stay city, for lodging."},
            "depart": {"type": "string", "description": "Outbound date, YYYY-MM-DD."},
            "ret": {"type": "string", "description": "Return date, YYYY-MM-DD."},
            "limit": {
                "type": "integer",
                "description": "How many observations to return. Default 20.",
            },
            **_COMMON,
        },
        "required": [],
    },
}
