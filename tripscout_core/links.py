"""Link di prenotazione per un'opzione trovata.

Il plugin non prenota e non ha chiavi: costruisce URL di ricerca **già impostati
su aeroporti e date esatte**, così dall'opzione si arriva alla pagina dove si
compra davvero. Sono link di ricerca, non di carrello: il prezzo finale lo dice
il venditore, non noi.
"""

from __future__ import annotations

from urllib.parse import quote_plus


def flight(origin_airport: str, dest_airport: str, depart: str, ret: str) -> str:
    """Google Flights, con la rotta e le date già dentro la query."""
    query = f"flights to {dest_airport} from {origin_airport} on {depart} through {ret}"
    return "https://www.google.com/travel/flights?q=" + quote_plus(query)


def stay(
    name: str,
    city: str,
    checkin: str,
    checkout: str,
    adults: int = 1,
    kind: str = "hotel",
) -> dict[str, str]:
    """La struttura cercata per nome su Google Hotels, più i portali per tipo."""
    adults = max(1, int(adults))
    return {
        "google": "https://www.google.com/travel/search?q=" + quote_plus(f"{name} {city}"),
        "booking": (
            "https://www.booking.com/searchresults.html?ss="
            + quote_plus(f"{name} {city}")
            + f"&checkin={checkin}&checkout={checkout}&group_adults={adults}&no_rooms=1"
            + "&selected_currency=EUR"
        ),
        "hostelworld": (
            "https://www.hostelworld.com/search?search_keywords="
            + quote_plus(city)
            + f"&date_from={checkin}&date_to={checkout}&number_of_guests={adults}"
        ),
        "airbnb": (
            "https://www.airbnb.com/s/" + quote_plus(city) + "/homes"
            f"?checkin={checkin}&checkout={checkout}&adults={adults}"
        ),
        "kind": kind,
    }


def ground(origin_city: str, airport: str) -> str:
    """Come arrivare in aeroporto coi mezzi pubblici dalla città di partenza."""
    return (
        "https://www.google.com/maps/dir/?api=1&origin="
        + quote_plus(origin_city)
        + "&destination=" + quote_plus(f"{airport} airport")
        + "&travelmode=transit"
    )


def transfer(airport: str, city: str) -> str:
    """Aeroporto ↔ centro città, mezzi pubblici."""
    return (
        "https://www.google.com/maps/dir/?api=1&origin="
        + quote_plus(f"{airport} airport")
        + "&destination=" + quote_plus(city)
        + "&travelmode=transit"
    )
