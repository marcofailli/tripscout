"""Ottimizzatore del viaggio completo.

Il punto del plugin: un volo economico non è un viaggio economico. Qui volo,
hotel e costo di adduzione agli aeroporti sono valutati **insieme**, sulla
stessa finestra di date, e il confronto è sul totale.

La ricerca è guidata dal budget: il prezzo dell'hotel si conosce prima di
quello del volo, quindi una combinazione già fuori budget viene scartata
senza spendere richieste sui voli.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Callable

from tripscout_core import store
from tripscout_core.flights import cheapest as cheapest_flight
from tripscout_core.grid import Trip
from tripscout_core.grid import trips as build_trips
from tripscout_core.hotels import search_stays
from tripscout_core.net import BudgetExhausted, GoogleBlocked, Session


@dataclass(slots=True)
class Origin:
    """Un aeroporto di partenza e quanto costa raggiungerlo (a persona, A/R)."""

    city: str
    airports: list[str]
    access_cost: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.city} ({'/'.join(self.airports)})"


@dataclass(slots=True)
class Destination:
    """Una città candidata; `transfer_cost` è aeroporto↔centro, a persona, a tratta."""

    city: str
    airports: list[str]
    country: str = ""
    transfer_cost: float = 0.0


@dataclass(slots=True)
class Spec:
    origins: list[Origin]
    destinations: list[Destination]
    window_start: date
    window_end: date
    nights_min: int = 2
    nights_max: int = 4
    weekdays: set[int] = field(default_factory=set)
    adults: int = 1
    rooms: int = 1
    budget_total: float | None = None
    currency: str = "EUR"
    language: str = "it"
    max_requests: int | None = 80
    max_options: int = 40
    top: int = 10
    min_interval: float = 1.0
    cache_ttl_hours: float = 12.0
    max_stops: int | None = None


@dataclass(slots=True)
class Option:
    """Un viaggio completo, con il dettaglio di come si compone il totale."""

    origin_city: str
    origin_airport: str
    dest_city: str
    dest_country: str
    dest_airport: str
    depart: str
    ret: str
    nights: int
    flight_price: float
    flight_total: float
    hotel_name: str
    hotel_total: float
    access_total: float
    transfer_total: float
    total: float
    currency: str
    airlines: list[str] = field(default_factory=list)
    stops: int | None = None
    flight_departure: str = ""
    flight_arrival: str = ""
    from_cache: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SweepResult:
    options: list[Option] = field(default_factory=list)
    best_per_destination: list[Option] = field(default_factory=list)
    partial: bool = False
    stopped_because: str = ""
    errors: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "options": [o.as_dict() for o in self.options],
            "best_per_destination": [o.as_dict() for o in self.best_per_destination],
            "partial": self.partial,
            "stopped_because": self.stopped_because,
            "errors": self.errors,
            "stats": self.stats,
        }


def flight_cache_key(
    origin_airport: str,
    dest_airport: str,
    depart: date,
    ret: date,
    *,
    adults: int,
    currency: str,
    max_stops: int | None = None,
) -> str:
    """Chiave di cache di un volo. Il formato è pubblico: serve anche allo storico."""
    return (
        f"{origin_airport}>{dest_airport}:{depart.isoformat()}:{ret.isoformat()}:"
        f"a{adults}:s{max_stops}:{currency}"
    )


def hotel_cache_key(
    city: str,
    depart: date,
    ret: date,
    *,
    adults: int,
    rooms: int,
    currency: str,
) -> str:
    """Chiave di cache di un soggiorno: una per città e date, non per aeroporto."""
    return (
        f"{city.casefold()}:{depart.isoformat()}:{ret.isoformat()}:"
        f"a{adults}:r{rooms}:{currency}"
    )


def _flight_key(origin: str, dest: str, trip: Trip, spec: Spec) -> str:
    return flight_cache_key(
        origin, dest, trip.depart, trip.ret,
        adults=spec.adults, currency=spec.currency, max_stops=spec.max_stops,
    )


def _hotel_key(city: str, trip: Trip, spec: Spec) -> str:
    return hotel_cache_key(
        city, trip.depart, trip.ret,
        adults=spec.adults, rooms=spec.rooms, currency=spec.currency,
    )


def sweep(
    spec: Spec,
    *,
    session: Session | None = None,
    progress: Callable[[str], None] | None = None,
) -> SweepResult:
    """Valuta ogni combinazione nella griglia e ordina per costo totale."""
    started = time.time()
    session = session or Session(
        min_interval=spec.min_interval, max_requests=spec.max_requests
    )
    result = SweepResult()
    if spec.destinations and spec.origins:
        min_access = min(o.access_cost for o in spec.origins)
    else:
        min_access = 0.0
    cache_hits = flights_fetched = hotels_fetched = pruned = 0
    trips_list = build_trips(
        spec.window_start,
        spec.window_end,
        spec.nights_min,
        spec.nights_max,
        spec.weekdays or None,
        spec.max_options,
    )
    if not trips_list:
        result.stopped_because = "nessuna finestra di date valida nella finestra richiesta"
        return result

    best_by_dest: dict[tuple[str, str], Option] = {}
    stop = False
    for destination in spec.destinations:
        if stop:
            break
        for trip in trips_list:
            if stop:
                break
            # 1. hotel: una richiesta copre tutte le partenze, e il prezzo si
            #    conosce prima del volo.
            hkey = _hotel_key(destination.city, trip, spec)
            blob = store.get("hotel", hkey, spec.cache_ttl_hours)
            if blob is not None:
                cache_hits += 1
                cheapest_stay = blob or None
            else:
                try:
                    stays = search_stays(
                        session,
                        destination.city,
                        trip.depart,
                        trip.ret,
                        currency=spec.currency,
                        language=spec.language,
                        adults=max(2, spec.adults),
                        rooms=spec.rooms,
                    )
                    hotels_fetched += 1
                    affordable = [s for s in stays if s.usable]
                    cheapest_stay = asdict(affordable[0]) if affordable else None
                    store.put("hotel", hkey, cheapest_stay)
                    if cheapest_stay:
                        store.record_price(
                            "hotel", hkey, cheapest_stay.get("total_price"), spec.currency
                        )
                except BudgetExhausted:
                    result.partial = True
                    result.stopped_because = "budget di richieste esaurito sugli hotel"
                    stop = True
                    continue
                except GoogleBlocked as exc:
                    result.errors.append(f"hotel {destination.city}: {exc}")
                    continue
                except Exception as exc:  # rete o parsing
                    result.errors.append(f"hotel {destination.city}: {type(exc).__name__}: {exc}")
                    continue
            if not cheapest_stay:
                continue
            hotel_total = float(cheapest_stay.get("total_price") or 0.0)
            if hotel_total <= 0:
                continue

            # 2. potatura guidata dal budget: se l'hotel da solo sfonda il tetto,
            #    i voli per questa combinazione non si cercano nemmeno.
            if spec.budget_total is not None:
                floor = (
                    hotel_total
                    + min_access * spec.adults
                    + destination.transfer_cost * 2 * spec.adults
                )
                if floor > spec.budget_total:
                    pruned += 1
                    continue

            # 3. voli: per ogni aeroporto di partenza, e per ogni aeroporto di
            #    arrivo si tiene solo la combinazione migliore.
            for origin in spec.origins:
                for origin_airport in origin.airports:
                    for dest_airport in destination.airports:
                        fkey = _flight_key(origin_airport, dest_airport, trip, spec)
                        cached = store.get("flight", fkey, spec.cache_ttl_hours)
                        if cached is not None:
                            cache_hits += 1
                            offer = cached
                        else:
                            try:
                                live = cheapest_flight(
                                    session,
                                    origin=origin_airport,
                                    destination=dest_airport,
                                    depart=trip.depart,
                                    ret=trip.ret,
                                    adults=spec.adults,
                                    currency=spec.currency,
                                    language=spec.language,
                                    max_stops=spec.max_stops,
                                )
                                flights_fetched += 1
                                offer = {
                                    "price": live.price,
                                    "airlines": live.airlines,
                                    "stops": live.stops,
                                    "departure": live.departure,
                                    "arrival": live.arrival,
                                }
                                store.put("flight", fkey, offer)
                                store.record_price("flight", fkey, live.price, spec.currency)
                            except BudgetExhausted:
                                result.partial = True
                                result.stopped_because = "budget di richieste esaurito sui voli"
                                stop = True
                                break
                            except GoogleBlocked as exc:
                                result.errors.append(
                                    f"volo {origin_airport}>{dest_airport}: {exc}"
                                )
                                continue
                            except Exception as exc:
                                result.errors.append(
                                    f"volo {origin_airport}>{dest_airport}: "
                                    f"{type(exc).__name__}: {exc}"
                                )
                                continue
                        if not offer or not offer.get("price"):
                            continue
                        flight_price = float(offer["price"])
                        access_total = origin.access_cost * spec.adults
                        transfer_total = destination.transfer_cost * 2 * spec.adults
                        total = (
                            flight_price * spec.adults
                            + hotel_total
                            + access_total
                            + transfer_total
                        )
                        option = Option(
                            origin_city=origin.city,
                            origin_airport=origin_airport,
                            dest_city=destination.city,
                            dest_country=destination.country,
                            dest_airport=dest_airport,
                            depart=trip.depart.isoformat(),
                            ret=trip.ret.isoformat(),
                            nights=trip.nights,
                            flight_price=flight_price,
                            flight_total=flight_price * spec.adults,
                            hotel_name=str(cheapest_stay.get("name") or ""),
                            hotel_total=hotel_total,
                            access_total=access_total,
                            transfer_total=transfer_total,
                            total=total,
                            currency=spec.currency,
                            airlines=list(offer.get("airlines") or []),
                            stops=offer.get("stops"),
                            flight_departure=str(offer.get("departure") or ""),
                            flight_arrival=str(offer.get("arrival") or ""),
                            from_cache=cached is not None,
                        )
                        key = (destination.city, trip.label)
                        previous = best_by_dest.get(key)
                        if previous is None or option.total < previous.total:
                            best_by_dest[key] = option
                if stop:
                    break
        if progress:
            progress(f"{destination.city}: {len(best_by_dest)} combinazioni valutate")

    options = sorted(best_by_dest.values(), key=lambda o: o.total)
    if spec.budget_total is not None:
        within = [o for o in options if o.total <= spec.budget_total]
        result.options = (within or options)[: spec.top]
        result.partial = result.partial or not within
        if not within:
            result.stopped_because = (
                result.stopped_because
                or "nessuna combinazione entro il budget: mostrate le più vicine"
            )
    else:
        result.options = options[: spec.top]

    per_dest: dict[str, Option] = {}
    for option in options:
        current = per_dest.get(option.dest_city)
        if current is None or option.total < current.total:
            per_dest[option.dest_city] = option
    result.best_per_destination = sorted(per_dest.values(), key=lambda o: o.total)

    result.stats = {
        "trips_considered": len(trips_list) * len(spec.destinations),
        "combinations_ranked": len(best_by_dest),
        "pruned_on_hotel_price": pruned,
        "flights_fetched": flights_fetched,
        "hotels_fetched": hotels_fetched,
        "cache_hits": cache_hits,
        "requests_spent": session.requests,
        "retries": session.retries,
        "elapsed_seconds": round(time.time() - started, 1),
        "currency": spec.currency,
    }
    return result


def price_one(
    spec: Spec,
    *,
    origin_airport: str,
    dest_city: str,
    dest_airport: str,
    depart: date,
    ret: date,
    origin_city: str = "",
    access_cost: float = 0.0,
    transfer_cost: float = 0.0,
    session: Session | None = None,
) -> dict[str, Any]:
    """Prezzo di un singolo viaggio, con il dettaglio voce per voce."""
    session = session or Session(min_interval=spec.min_interval, max_requests=4)
    trip = Trip(depart=depart, ret=ret, nights=(ret - depart).days)
    stays = search_stays(
        session,
        dest_city,
        depart,
        ret,
        currency=spec.currency,
        language=spec.language,
        adults=max(2, spec.adults),
        rooms=spec.rooms,
    )
    affordable = [s for s in stays if s.usable]
    offer = cheapest_flight(
        session,
        origin=origin_airport,
        destination=dest_airport,
        depart=depart,
        ret=ret,
        adults=spec.adults,
        currency=spec.currency,
        language=spec.language,
        max_stops=spec.max_stops,
    )
    hotel_total = float(affordable[0].total_price) if affordable else 0.0
    flight_price = float(offer.price) if offer.usable else 0.0
    access_total = access_cost * spec.adults
    transfer_total = transfer_cost * 2 * spec.adults
    return {
        "trip": {
            "origin_city": origin_city or origin_airport,
            "origin_airport": origin_airport,
            "dest_city": dest_city,
            "dest_airport": dest_airport,
            "depart": trip.depart.isoformat(),
            "ret": trip.ret.isoformat(),
            "nights": trip.nights,
            "adults": spec.adults,
            "rooms": spec.rooms,
        },
        "flight": {
            "price_per_person": flight_price or None,
            "airlines": offer.airlines,
            "stops": offer.stops,
            "departure": offer.departure,
            "arrival": offer.arrival,
        },
        "hotel": {
            "name": affordable[0].name if affordable else None,
            "stay_total": hotel_total or None,
            "alternatives": [
                {"name": s.name, "stay_total": s.total_price} for s in affordable[1:6]
            ],
        },
        "breakdown": {
            "flight_total": flight_price * spec.adults,
            "hotel_total": hotel_total,
            "access_total": access_total,
            "airport_transfer_total": transfer_total,
            "total": flight_price * spec.adults + hotel_total + access_total + transfer_total,
        },
        "currency": spec.currency,
        "requests_spent": session.requests,
    }
