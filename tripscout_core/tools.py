"""Implementazione dei tre tool: ricerca congiunta, prezzo puntuale, storico."""

from __future__ import annotations

import datetime as dt
import json
from datetime import date, timedelta
from typing import Any

from tripscout_core import links, store
from tripscout_core.grid import parse_weekdays, weekend_windows
from tripscout_core.net import Session
from tripscout_core.optimizer import (
    Destination,
    Option,
    Origin,
    Spec,
    flight_cache_key,
    hotel_cache_key,
    price_one,
    sweep,
)


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _date(value: Any, *, default: date | None = None, field: str = "data") -> date | None:
    if value in (None, "", "null"):
        return default
    if isinstance(value, date):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ValueError(
            f"invalid {field or 'date'}: {value!r} (expected YYYY-MM-DD)"
        ) from exc


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _opt_num(value: Any) -> float | None:
    """Numero facoltativo: None quando non è stato dato (non 0)."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _lodging(value: Any) -> set[str]:
    """Categorie di alloggio richieste; default 'any'."""
    from tripscout_core.hotels import _parse_lodging

    return _parse_lodging(value)


def _known_cities() -> list[str]:
    from tripscout_core.origins import known_cities

    return known_cities()


def origins(params: dict | None = None, **_kwargs: Any) -> str:
    """Elenca (o risolve) le città di partenza note, con aeroporti e costi."""
    params = params or {}
    from tripscout_core.origins import known_cities, resolve

    city = params.get("city")
    if city:
        preset = resolve(city)
        if preset is None:
            return _json(
                {
                    "error": f"'{city}' is not a known departure city.",
                    "known_cities": known_cities(),
                }
            )
        return _json(
            {
                "city": preset.city,
                "region": preset.region,
                "airports": [
                    {
                        "airport": a.airport,
                        "airport_city": a.airport_city,
                        "access_cost": a.access_cost,
                        "how": a.how,
                    }
                    for a in preset.airports
                ],
                "origins_param": preset.as_origins(),
                "note": (
                    "access_cost is per person, return trip, and is an estimate for cheap "
                    "travel (train, bus, shuttle). Override it by passing 'origins' yourself."
                ),
            }
        )

    cities = []
    for name in known_cities():
        preset = resolve(name)
        if preset is None:
            continue
        cities.append(
            {
                "city": preset.city,
                "region": preset.region,
                "airports": [
                    {"airport": a.airport, "access_cost": a.access_cost}
                    for a in preset.airports
                ],
            }
        )
    return _json(
        {
            "count": len(cities),
            "cities": cities,
            "note": (
                "Pass one of these as 'home' in tripscout_search and the departure airports "
                "and their ground costs are filled in automatically."
            ),
        }
    )


def _origins(raw: Any) -> list[Origin]:
    out: list[Origin] = []
    for item in _as_list(raw):
        if not isinstance(item, dict):
            continue
        airports = [
            str(a).strip().upper() for a in _as_list(item.get("airports")) if str(a).strip()
        ]
        if not airports:
            continue
        out.append(
            Origin(
                city=str(item.get("city") or airports[0]),
                airports=airports,
                access_cost=_num(item.get("access_cost")),
            )
        )
    return out


def _destinations(raw: Any) -> list[Destination]:
    from tripscout_core.cities import resolve as resolve_city

    out: list[Destination] = []
    for item in _as_list(raw):
        if isinstance(item, str):
            preset = resolve_city(item)
            if preset is not None:
                out.append(
                    Destination(
                        city=preset.city,
                        airports=list(preset.airports),
                        country=preset.country,
                        transfer_cost=preset.transfer_cost,
                    )
                )
            else:
                out.append(Destination(city=item, airports=[]))
            continue
        if not isinstance(item, dict):
            continue
        city = str(item.get("city") or "").strip()
        airports = [
            str(a).strip().upper() for a in _as_list(item.get("airports")) if str(a).strip()
        ]
        if not city:
            continue
        country = str(item.get("country") or "")
        transfer = _num(item.get("transfer_cost"))
        if not airports or not country:
            # nome città noto -> aeroporti, paese e transfer dalla tabella
            preset = resolve_city(city)
            if preset is not None:
                airports = airports or list(preset.airports)
                country = country or preset.country
                transfer = transfer or preset.transfer_cost
        out.append(
            Destination(
                city=city,
                airports=airports,
                country=country,
                transfer_cost=transfer,
            )
        )
    return out


def _spec(params: dict, *, origins: list[Origin], destinations: list[Destination],
          window_start: date, window_end: date) -> Spec:
    # `weekdays` assente = default comodo per l'agente (giovedì e venerdì);
    # `weekdays` presente ma vuoto (o ["any"]) = nessun filtro, si parte ogni giorno.
    if params.get("weekdays") is None:
        weekdays = {3, 4}
    else:
        weekdays = parse_weekdays(params.get("weekdays"))
    budget = params.get("budget_total")
    return Spec(
        origins=origins,
        destinations=destinations,
        window_start=window_start,
        window_end=window_end,
        nights_min=_int(params.get("nights_min"), 2),
        nights_max=_int(params.get("nights_max"), 4),
        weekdays=weekdays,
        adults=max(1, _int(params.get("adults"), 1)),
        rooms=max(1, _int(params.get("rooms"), 1)),
        budget_total=_num(budget) if budget not in (None, "") else None,
        currency=str(params.get("currency") or "EUR"),
        language=str(params.get("language") or "it"),
        max_requests=_int(params.get("max_requests"), 80),
        max_options=max(1, _int(params.get("max_options"), 40)),
        top=max(1, _int(params.get("top"), 10)),
        min_interval=_num(params.get("min_interval"), 1.0),
        cache_ttl_hours=_num(params.get("cache_ttl_hours"), 12.0),
        max_stops=(
            _int(params.get("max_stops"), 99) if params.get("max_stops") is not None else None
        ),
        lodging=_lodging(params.get("lodging")),
        estimates=bool(params.get("estimates")),
        food_per_day=_opt_num(params.get("food_per_day")),
        activities_per_day=_opt_num(params.get("activities_per_day")),
    )


def _line(option: Option, adults: int = 1, home: str | None = None) -> dict[str, Any]:
    """Un'opzione in forma leggibile più i numeri grezzi, per il modello."""
    return {
        "city": f"{option.dest_city}" + (f" ({option.dest_country})" if option.dest_country else ""),
        "dates": f"{option.depart} → {option.ret} ({option.nights} notti)",
        "from": f"{option.origin_city} {option.origin_airport}",
        "total": round(option.total, 2),
        "total_text": f"{option.total:.0f} {option.currency}",
        "currency": option.currency,
        "flight": round(option.flight_total, 2),
        "hotel": round(option.hotel_total, 2),
        "hotel_name": option.hotel_name,
        "lodging_kind": option.lodging_kind,
        "access": round(option.access_total, 2),
        "airport_transfer": round(option.transfer_total, 2),
        "total_with_estimates": option.total_with_estimates,
        "estimate": option.estimate,
        "breakdown_text": (
            f"flight {option.flight_total:.0f} + stay {option.hotel_total:.0f} "
            f"({option.hotel_name}, {option.lodging_kind}) + access {option.access_total:.0f} + "
            f"transfer {option.transfer_total:.0f} = {option.total:.0f} {option.currency}"
        ),
        "airlines": option.airlines,
        "stops": option.stops,
        "flight_departure": option.flight_departure,
        "flight_arrival": option.flight_arrival,
        "from_cache": option.from_cache,
        "links": (
            {
                "flight": links.flight(
                    option.origin_airport, option.dest_airport, option.depart, option.ret
                ),
                "stay": links.stay(
                    option.hotel_name,
                    option.dest_city,
                    option.depart,
                    option.ret,
                    adults=max(1, adults),
                    kind=option.lodging_kind,
                ),
                "ground": links.ground(home or option.origin_city, option.origin_airport),
                "transfer": links.transfer(option.dest_airport, option.dest_city),
            }
            if option.origin_airport and option.dest_airport
            else {}
        ),
    }


def search(params: dict | None = None, **_kwargs: Any) -> str:
    """Ricerca congiunta su tutta la griglia."""
    params = params or {}
    origins = _origins(params.get("origins"))
    # la città di casa serve ai link "come arrivo in aeroporto": è il punto di
    # partenza del viaggio, non la città dell'aeroporto
    home = (params.get("home") or params.get("from_city") or "").strip() or None
    resolved_from = ""
    origin_note = ""
    if not origins:
        from tripscout_core.origins import resolve_any

        preset = resolve_any(home)
        if preset is not None:
            origins = _origins(preset.as_origins())
            resolved_from = preset.city
            if preset.region == "geocoded":
                looked = ", ".join(
                    f"{a.airport_city} ({a.airport}) ~{a.access_cost:.0f} EUR" for a in preset.airports
                )
                origin_note = (
                    f"{preset.city} was looked up on the map: nearest airports with scheduled "
                    f"flights are {looked}. Ground costs are distance estimates, not timetables."
                )
    destinations = _destinations(params.get("destinations"))
    if not origins:
        known = _known_cities()
        return _json(
            {
                "error": (
                    "departure not understood: pass 'origins' explicitly, or 'home' with a place "
                    "name — any town on earth works (looked up on OpenStreetMap). "
                    + (f"Known presets: {', '.join(str(c) for c in known)}." if known else "")
                )
            }
        )
    if not destinations:
        return _json({"error": "at least one candidate city is required in 'destinations'."})

    try:
        window_start = _date(params.get("window_start"), field="window_start")
        window_end = _date(params.get("window_end"), field="window_end")
    except ValueError as exc:
        return _json({"error": str(exc)})
    weekends = max(1, _int(params.get("weekends"), 2))
    if window_start is None:
        spans = weekend_windows(weekends)
        window_start, default_end = spans[0][0], spans[-1][1]
    else:
        default_end = window_start + timedelta(days=21)
    window_end = window_end or default_end
    if window_end < window_start:
        return _json({"error": "window_end is before window_start."})

    spec = _spec(
        params,
        origins=origins,
        destinations=destinations,
        window_start=window_start,
        window_end=window_end,
    )
    destinations_missing_airports = [d.city for d in spec.destinations if not d.airports]
    if destinations_missing_airports:
        return _json(
            {
                "error": (
                    "every destination needs its airports (IATA) to price flights: "
                    + ", ".join(destinations_missing_airports)
                )
            }
        )

    session = Session(min_interval=spec.min_interval, max_requests=spec.max_requests)
    result = sweep(spec, session=session)

    notes: list[str] = []
    if origin_note:
        notes.append(origin_note)
    elif resolved_from:
        detail = "; ".join(
            f"{o.label} ~{o.access_cost:.0f} {spec.currency}" for o in spec.origins
        )
        notes.append(
            f"Departure resolved from {resolved_from}: {detail}. "
            "Those ground costs are estimates for cheap travel, not a timetable."
        )
    if result.partial:
        notes.append(
            "Partial results: " + (result.stopped_because or "search stopped early.")
        )
    if result.errors:
        notes.append(f"{len(result.errors)} requests failed (details in 'errors').")
    if not result.options:
        notes.append("No usable combination: widen the dates, the budget or the cities.")
    notes.append(
        "Lodging prices are totals for the whole stay on the dates shown, not per night; "
        "the flight price is per person."
    )
    if spec.estimates:
        from tripscout_core.estimates import ESTIMATE_DISCLAIMER

        notes.append(ESTIMATE_DISCLAIMER)
        notes.append(
            "The ranking uses the bookable total (flight, stay, airport access, transfer); "
            "'total_with_estimates' adds food and attractions but does not reorder the list."
        )
    if "any" not in spec.lodging:
        notes.append(
            "Lodging filtered to: " + ", ".join(sorted(spec.lodging))
            + ". Apartments cost one extra request per city and date."
        )

    out: dict[str, Any] = {
        "method": (
            "Flights and lodging priced together on the same dates; total = flight×travellers + "
            "stay + ground access to the airport + airport-to-town transfer."
        ),
        "query": {
            "origins": [o.label for o in spec.origins],
            "destinations": [d.city for d in spec.destinations],
            "window": f"{spec.window_start} → {spec.window_end}",
            "nights": f"{spec.nights_min}-{spec.nights_max}",
            "departure_weekdays": sorted(spec.weekdays),
            "adults": spec.adults,
            "rooms": spec.rooms,
            "budget_total": spec.budget_total,
            "currency": spec.currency,
            "lodging": sorted(spec.lodging),
            "estimates": spec.estimates,
            "resolved_from": resolved_from or None,
        },
        "best": _line(result.options[0], spec.adults, home) if result.options else None,
        "options": [_line(o, spec.adults, home) for o in result.options],
        "best_per_destination": [_line(o, spec.adults, home) for o in result.best_per_destination],
        "notes": notes,
        "stats": result.stats,
    }
    if result.errors:
        out["errors"] = result.errors[:10]
    return _json(out)


def price_trip(params: dict | None = None, **_kwargs: Any) -> str:
    """Prezzo di un singolo viaggio, con dettaglio voce per voce."""
    params = params or {}
    try:
        depart = _date(params.get("depart"), field="depart")
        ret = _date(params.get("ret"), field="ret")
    except ValueError as exc:
        return _json({"error": str(exc)})
    if not depart or not ret:
        return _json({"error": "'depart' and 'ret' are required, as YYYY-MM-DD."})
    if ret <= depart:
        return _json({"error": "'ret' must be after 'depart'."})

    origin_airport = str(params.get("origin_airport") or "").strip().upper()
    dest_airport = str(params.get("dest_airport") or "").strip().upper()
    dest_city = str(params.get("dest_city") or "").strip()
    if not (origin_airport and dest_airport and dest_city):
        return _json({"error": "origin_airport, dest_airport and dest_city are required."})

    spec = _spec(
        params,
        origins=[Origin(city=str(params.get("origin_city") or origin_airport),
                         airports=[origin_airport],
                         access_cost=_num(params.get("access_cost")))],
        destinations=[Destination(city=dest_city, airports=[dest_airport],
                                  country=str(params.get("country") or ""),
                                  transfer_cost=_num(params.get("transfer_cost")))],
        window_start=depart,
        window_end=ret,
    )
    session = Session(min_interval=spec.min_interval, max_requests=4)
    detail = price_one(
        spec,
        origin_airport=origin_airport,
        origin_city=str(params.get("origin_city") or ""),
        access_cost=spec.origins[0].access_cost,
        dest_city=dest_city,
        dest_airport=dest_airport,
        transfer_cost=spec.destinations[0].transfer_cost,
        depart=depart,
        ret=ret,
        session=session,
    )
    detail["notes"] = [
        "The flight is per person; the stay is the total for those nights for the number of rooms.",
        "If 'flight.price_per_person' or 'hotel.stay_total' is null, that source returned no "
        "prices for these dates: try again in a moment.",
    ]
    return _json(detail)


def history(params: dict | None = None, **_kwargs: Any) -> str:
    """Storico dei prezzi osservati e inventario della cache (nessuna richiesta di rete)."""
    params = params or {}
    kind = str(params.get("kind") or "all").casefold()
    limit = max(1, _int(params.get("limit"), 20))
    out: dict[str, Any] = {"cache": store.cache_stats(), "currency": params.get("currency") or "EUR"}

    depart = _date(params.get("depart"), field="depart")
    ret = _date(params.get("ret"), field="ret")
    adults = max(1, _int(params.get("adults"), 1))
    rooms = max(1, _int(params.get("rooms"), 1))
    currency = str(params.get("currency") or "EUR")

    if kind in ("flight", "all") and (params.get("origin_airport") and params.get("dest_airport") and depart and ret):
        key = flight_cache_key(
            str(params["origin_airport"]).upper(),
            str(params["dest_airport"]).upper(),
            depart, ret, adults=adults, currency=currency,
            max_stops=params.get("max_stops"),
        )
        out["flight"] = {
            "key": key,
            "cached": store.get("flight", key, -1),
            "observations": store.price_history("flight", key, limit),
        }
    if kind in ("hotel", "all") and (params.get("dest_city") and depart and ret):
        key = hotel_cache_key(str(params["dest_city"]), depart, ret,
                              adults=adults, rooms=rooms, currency=currency)
        out["hotel"] = {
            "key": key,
            "cached": store.get("hotel", key, -1),
            "observations": store.price_history("hotel", key, limit),
        }
    if "flight" not in out and "hotel" not in out:
        out["note"] = (
            "A flight history needs origin_airport, dest_airport, depart and ret; "
            "a stay history needs dest_city, depart and ret."
        )
    return _json(out)
