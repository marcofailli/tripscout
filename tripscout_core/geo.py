"""Da un posto qualsiasi agli aeroporti vicini.

La città di partenza non è più un elenco chiuso: si scrive "Agerola", "Barolo"
o "Reykjavik" e il plugin geocodifica il nome (Nominatim/OpenStreetMap, nessuna
chiave) e cerca gli aeroporti di linea entro un raggio ragionevole nella tabella
locale (OurAirports, pubblico dominio, 4008 scali).

Due scelte dichiarate:
- i costi di adduzione sono **stime** sulla distanza (treno/bus), non orari;
- se il geocoding non risponde, si ricade sui preset scritti a mano e, se
  nemmeno quelli bastano, si dice che non si sa: non si inventa un aeroporto.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA = Path(__file__).with_name("data") / "airports.csv.gz"
USER_AGENT = "tripscout-hermes-plugin/0.3.7 (+https://github.com/marcofailli/tripscout)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"

MAX_AIRPORTS = 3
SEARCH_RADIUS_KM = 400.0
DISTANCE_FACTOR = 4.0   # tiene un aeroporto se entro 4x il più vicino
MIN_RADIUS_KM = 60.0

_last_geocode = 0.0


@dataclass(slots=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    lat: float
    lon: float


_airports: list[Airport] | None = None


def airports() -> list[Airport]:
    """Carica la tabella una volta sola (4008 righe, ~115 KB compressi)."""
    global _airports
    if _airports is None:
        rows: list[Airport] = []
        with gzip.open(DATA, "rt", encoding="utf-8", newline="") as fh:
            for record in csv.DictReader(fh):
                try:
                    rows.append(
                        Airport(
                            iata=record["iata"],
                            name=record["name"],
                            city=record["city"] or record["name"],
                            country=record["country"],
                            lat=float(record["lat"]),
                            lon=float(record["lon"]),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        _airports = rows
    return _airports


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearest(lat: float, lon: float, *, limit: int = MAX_AIRPORTS) -> list[tuple[Airport, float]]:
    """Gli aeroporti più vicini, senza prendere scali a 300 km se ce n'è uno a 20."""
    scored = [
        (airport, haversine_km(lat, lon, airport.lat, airport.lon))
        for airport in airports()
    ]
    scored = [(a, d) for a, d in scored if d <= SEARCH_RADIUS_KM]
    scored.sort(key=lambda item: item[1])
    if not scored:
        return []
    cutoff = max(scored[0][1] * DISTANCE_FACTOR, MIN_RADIUS_KM)
    return [(a, d) for a, d in scored if d <= cutoff][:limit]


def access_estimate(km: float) -> tuple[float, str]:
    """Costo andata e ritorno a persona per raggiungere l'aeroporto.

    Tariffa base più un costo chilometrico da regionale: sui casi noti (Prato →
    Firenze/Pisa/Bologna) restituisce 8.5 / 16.6 / 20.2 EUR, vicino ai valori
    scritti a mano nei preset (9 / 16 / 24).
    """
    one_way = min(45.0, 2.0 + 0.09 * km)
    return round(one_way * 2, 1), f"~{km:.0f} km by train or bus (estimate)"


def geocode(place: str, *, timeout: float = 8.0) -> tuple[float, float, str] | None:
    """Nome di un posto -> coordinate. Cache in SQLite, una richiesta al secondo."""
    global _last_geocode
    cleaned = " ".join(place.split())
    if not cleaned:
        return None
    key = f"nominatim:{cleaned.casefold()}"
    try:
        from tripscout_core import store

        cached = store.get("geo", key, 24 * 30)
    except Exception:  # noqa: BLE001 — la cache non deve mai impedire la ricerca
        cached = None
    if cached:
        return float(cached["lat"]), float(cached["lon"]), str(cached.get("display") or cleaned)

    wait = 1.1 - (time.time() - _last_geocode)
    if wait > 0:
        time.sleep(wait)
    query = urllib.parse.urlencode(
        {"q": cleaned, "format": "jsonv2", "limit": 1, "accept-language": "en"}
    )
    request = urllib.request.Request(
        f"{NOMINATIM}?{query}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        _last_geocode = time.time()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not payload:
        return None
    best = payload[0]
    try:
        lat, lon = float(best["lat"]), float(best["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    display = str(best.get("display_name") or cleaned)
    try:
        from tripscout_core import store

        store.put("geo", key, {"lat": lat, "lon": lon, "display": display})
    except Exception:  # noqa: BLE001
        pass
    return lat, lon, display


def resolve(place: str) -> dict[str, Any] | None:
    """Posto qualsiasi -> città + aeroporti vicini con costo stimato."""
    located = geocode(place)
    if located is None:
        return None
    lat, lon, display = located
    found = nearest(lat, lon)
    if not found:
        return None
    short = display.split(",")[0].strip() or place
    airports_out = []
    for airport, km in found:
        cost, how = access_estimate(km)
        airports_out.append(
            {
                "airport": airport.iata,
                "airport_city": airport.city or airport.name,
                "access_cost": cost,
                "how": how,
                "distance_km": round(km, 1),
            }
        )
    return {
        "city": short,
        "display_name": display,
        "lat": lat,
        "lon": lon,
        "airports": airports_out,
        "source": "geocode",
    }
