"""Voli da Google Flights.

`fast-flights` costruisce il protobuf `tfs` della query e interpreta la pagina
dei risultati; il trasporto è nostro (`core.net.Session`) perché quello di
default non porta il cookie di consenso e in UE incassa l'interstiziale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from tripscout_core.net import MISSING_DEP, Session

FLIGHTS_URL = "https://www.google.com/travel/flights"


@dataclass(slots=True)
class Offer:
    """Offerta di volo più economica trovata per una rotta e una data."""

    price: float | None
    currency: str
    airlines: list[str] = field(default_factory=list)
    stops: int | None = None
    duration_minutes: int | None = None
    departure: str = ""
    arrival: str = ""
    itineraries: int = 0

    @property
    def usable(self) -> bool:
        return self.price is not None and self.price > 0


def _fast_flights():
    """Importa `fast-flights` solo quando serve, con un errore comprensibile."""
    try:
        from fast_flights import FlightQuery, Passengers, create_query
        from fast_flights.parser import parse
    except ModuleNotFoundError as exc:  # dipendenza dichiarata nel manifest
        raise RuntimeError(MISSING_DEP) from exc
    return FlightQuery, Passengers, create_query, parse


def _hhmm(value) -> str:
    """SimpleDatetime -> 'YYYY-MM-DD HH:MM' (o stringa vuota)."""
    try:
        y, m, d = value.date
        hh, mm = value.time
        return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}"
    except Exception:
        return ""


def cheapest(
    session: Session,
    *,
    origin: str,
    destination: str,
    depart: date,
    ret: date | None = None,
    adults: int = 1,
    currency: str = "EUR",
    language: str = "it",
    max_stops: int | None = None,
) -> Offer:
    """Offerta più economica da `origin` a `destination`, andata (+ ritorno).

    Una sola richiesta copre andata e ritorno: la query è round-trip.
    """
    FlightQuery, Passengers, create_query, parse = _fast_flights()
    legs = [FlightQuery(date=depart.isoformat(), from_airport=origin,
                        to_airport=destination, max_stops=max_stops)]
    if ret is not None:
        legs.append(FlightQuery(date=ret.isoformat(), from_airport=destination,
                                to_airport=origin, max_stops=max_stops))
    query = create_query(
        flights=legs,
        trip="round-trip" if ret is not None else "one-way",
        seat="economy",
        passengers=Passengers(adults=adults),
        currency=currency,
        language=language,
        max_stops=max_stops,
    )
    try:
        html = session.get(FLIGHTS_URL, params=query.params()).text
        results = parse(html)
    except (TypeError, AttributeError, IndexError, KeyError):
        # `fast-flights` non sa leggere una pagina senza risultati (payload[3] None):
        # equivale a "nessun volo su questa rotta in questa data", non a un errore.
        return Offer(price=None, currency=currency)
    offers = []
    for item in results:
        price = getattr(item, "price", None)
        if not isinstance(price, (int, float)) or price <= 0:
            continue
        legs_out = list(getattr(item, "flights", None) or [])
        first = legs_out[0] if legs_out else None
        # `airlines` è una lista di nomi (a volte di oggetti, secondo la versione)
        airlines: list[str] = []
        for entry in getattr(item, "airlines", None) or []:
            name = (
                getattr(entry, "name", None)
                or getattr(entry, "code", None)
                or (entry if isinstance(entry, str) else None)
            )
            if name:
                airlines.append(str(name))
        segments = len(legs_out)
        offers.append(
            Offer(
                price=float(price),
                currency=currency,
                airlines=airlines,
                # Con andata e ritorno `flights` contiene una tratta per direzione:
                # gli scali non sono deducibili, quindi non si dichiarano.
                stops=None if ret is not None else max(0, segments - 1),
                duration_minutes=sum(int(getattr(x, "duration", 0) or 0) for x in legs_out) or None,
                departure=_hhmm(first.departure) if first else "",
                arrival=_hhmm(first.arrival) if first else "",
                itineraries=segments,
            )
        )
    if not offers:
        return Offer(price=None, currency=currency)
    return min(offers, key=lambda o: o.price)
