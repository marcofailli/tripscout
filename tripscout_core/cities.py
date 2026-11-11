"""Destinazioni pronte: nome città -> aeroporti, paese e transfer in centro.

Serve a due cose che altrimenti restano a carico dell'utente: sapere che
"Vienna" significa VIE, e che dall'aeroporto al centro ci sono 4,5 € di
transfer. `transfer_cost` è a persona e a tratta.

Chi vuole una città non in tabella passa semplicemente `destinations`
espliciti con `city` e `airports`: la tabella è una scorciatoia, non un limite.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class CityPreset:
    city: str
    country: str
    airports: list[str]
    transfer_cost: float
    region: str = ""

    def as_destination(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "airports": list(self.airports),
            "country": self.country,
            "transfer_cost": self.transfer_cost,
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _c(city: str, country: str, airports: list[str], transfer: float, region: str) -> CityPreset:
    return CityPreset(city, country, airports, transfer, region)


_CITIES: list[CityPreset] = [
    # Europa centrale e orientale (il caso "spendere poco")
    _c("Budapest", "HU", ["BUD"], 3.5, "east"),
    _c("Vienna", "AT", ["VIE"], 4.5, "east"),
    _c("Praga", "CZ", ["PRG"], 3.0, "east"),
    _c("Cracovia", "PL", ["KRK"], 4.0, "east"),
    _c("Varsavia", "PL", ["WAW"], 3.5, "east"),
    _c("Danzica", "PL", ["GDN"], 3.0, "east"),
    _c("Bratislava", "SK", ["BTS"], 3.0, "east"),
    _c("Brno", "CZ", ["BRQ"], 3.0, "east"),
    _c("Lubiana", "SI", ["LJU"], 4.0, "east"),
    _c("Zagabria", "HR", ["ZAG"], 3.0, "east"),
    _c("Belgrado", "RS", ["BEG"], 3.0, "east"),
    _c("Budva", "ME", ["TIV"], 5.0, "east"),
    _c("Sofia", "BG", ["SOF"], 2.5, "east"),
    _c("Bucarest", "RO", ["OTP"], 3.0, "east"),
    _c("Cluj", "RO", ["CLJ"], 3.0, "east"),
    _c("Tallinn", "EE", ["TLL"], 3.0, "east"),
    _c("Riga", "LV", ["RIX"], 3.0, "east"),
    _c("Vilnius", "LT", ["VNO"], 2.5, "east"),
    # Baltico e nord
    _c("Copenaghen", "DK", ["CPH"], 5.5, "north"),
    _c("Stoccolma", "SE", ["ARN"], 6.0, "north"),
    _c("Oslo", "NO", ["OSL"], 7.0, "north"),
    _c("Helsinki", "FI", ["HEL"], 5.0, "north"),
    _c("Göteborg", "SE", ["GOT"], 5.0, "north"),
    # Europa occidentale
    _c("Berlino", "DE", ["BER"], 4.5, "west"),
    _c("Monaco di Baviera", "DE", ["MUC"], 6.0, "west"),
    _c("Amburgo", "DE", ["HAM"], 4.5, "west"),
    _c("Colonia", "DE", ["CGN"], 4.0, "west"),
    _c("Amsterdam", "NL", ["AMS"], 6.0, "west"),
    _c("Eindhoven", "NL", ["EIN"], 5.0, "west"),
    _c("Bruxelles", "BE", ["BRU"], 5.0, "west"),
    _c("Parigi", "FR", ["CDG", "ORY", "BVA"], 12.0, "west"),
    _c("Lione", "FR", ["LYS"], 4.5, "west"),
    _c("Marsiglia", "FR", ["MRS"], 4.0, "west"),
    _c("Nizza", "FR", ["NCE"], 4.0, "west"),
    _c("Londra", "GB", ["STN", "LTN", "LGW"], 14.0, "west"),
    _c("Dublino", "IE", ["DUB"], 6.0, "west"),
    _c("Zurigo", "CH", ["ZRH"], 6.5, "west"),
    _c("Ginevra", "CH", ["GVA"], 5.0, "west"),
    # Sud Europa
    _c("Madrid", "ES", ["MAD"], 5.0, "south"),
    _c("Barcellona", "ES", ["BCN"], 5.5, "south"),
    _c("Valencia", "ES", ["VLC"], 4.0, "south"),
    _c("Siviglia", "ES", ["SVQ"], 3.5, "south"),
    _c("Lisbona", "PT", ["LIS"], 4.0, "south"),
    _c("Porto", "PT", ["OPO"], 3.5, "south"),
    _c("Atene", "GR", ["ATH"], 6.0, "south"),
    _c("Salonicco", "GR", ["SKG"], 3.0, "south"),
    _c("La Valletta", "MT", ["MLA"], 3.0, "south"),
    _c("Santorini", "GR", ["JTR"], 6.0, "south"),
    _c("Istanbul", "TR", ["IST", "SAW"], 4.0, "south"),
]

_INDEX: dict[str, CityPreset] = {}
for _preset in _CITIES:
    _INDEX[_preset.city.casefold()] = _preset

_ALIASES = {
    "vienna": "Vienna",
    "wien": "Vienna",
    "prague": "Praga",
    "praha": "Praga",
    "krakow": "Cracovia",
    "kraków": "Cracovia",
    "warsaw": "Varsavia",
    "warszawa": "Varsavia",
    "gdansk": "Danzica",
    "bratislava": "Bratislava",
    "ljubljana": "Lubiana",
    "zagreb": "Zagabria",
    "belgrade": "Belgrado",
    "bucharest": "Bucarest",
    "copenhagen": "Copenaghen",
    "stockholm": "Stoccolma",
    "helsinki": "Helsinki",
    "berlin": "Berlino",
    "munich": "Monaco di Baviera",
    "muenchen": "Monaco di Baviera",
    "münchen": "Monaco di Baviera",
    "hamburg": "Amburgo",
    "cologne": "Colonia",
    "köln": "Colonia",
    "brussels": "Bruxelles",
    "paris": "Parigi",
    "lyon": "Lione",
    "marseille": "Marsiglia",
    "nice": "Nizza",
    "london": "Londra",
    "dublin": "Dublino",
    "zurich": "Zurigo",
    "zürich": "Zurigo",
    "geneva": "Ginevra",
    "madrid": "Madrid",
    "barcelona": "Barcellona",
    "valencia": "Valencia",
    "seville": "Siviglia",
    "lisbon": "Lisbona",
    "athens": "Atene",
    "thessaloniki": "Salonicco",
    "malta": "La Valletta",
    "istanbul": "Istanbul",
    "warsavia": "Varsavia",
    "copenhagen ": "Copenaghen",
}
for _alias, _canonical in _ALIASES.items():
    _INDEX.setdefault(_alias.casefold(), _INDEX[_canonical.casefold()])


def resolve(name: str | None) -> CityPreset | None:
    """Nome città -> preset, o None se non è in tabella.

    Accetta il nome canonico (italiano), quello inglese e le varianti con
    nazione fra parentesi, così il pannello può mostrare "Prague" e rimandare
    indietro "Prague" senza che il backend si confonda.
    """
    if not name:
        return None
    key = " ".join(str(name).strip().casefold().split())
    if key in _INDEX:
        return _INDEX[key]
    head = key.replace(",", " ").split("(")[0].strip()
    found = _INDEX.get(head)
    if found is not None:
        return found
    for canonical, label in EN_NAMES.items():
        if label.casefold() == head:
            return _INDEX.get(canonical.casefold())
    return None


def all_cities(region: str | None = None) -> list[CityPreset]:
    if region:
        wanted = region.strip().casefold()
        return [c for c in _CITIES if c.region == wanted]
    return list(_CITIES)


def regions() -> list[str]:
    seen: list[str] = []
    for preset in _CITIES:
        if preset.region and preset.region not in seen:
            seen.append(preset.region)
    return seen


# Nomi inglesi: il plugin e il suo catalogo sono English-first, e le città
# italiane ("Londra", "Cracovia") stonano in un output inglese. La chiave resta
# il nome canonico (quello italiano), che serve anche per la ricerca su Google.
EN_NAMES = {
    "Praga": "Prague",
    "Cracovia": "Krakow",
    "Varsavia": "Warsaw",
    "Danzica": "Gdansk",
    "Lubiana": "Ljubljana",
    "Zagabria": "Zagreb",
    "Belgrado": "Belgrade",
    "Bucarest": "Bucharest",
    "Cluj": "Cluj-Napoca",
    "Copenaghen": "Copenhagen",
    "Stoccolma": "Stockholm",
    "Göteborg": "Gothenburg",
    "Berlino": "Berlin",
    "Monaco di Baviera": "Munich",
    "Amburgo": "Hamburg",
    "Colonia": "Cologne",
    "Bruxelles": "Brussels",
    "Parigi": "Paris",
    "Lione": "Lyon",
    "Marsiglia": "Marseille",
    "Nizza": "Nice",
    "Londra": "London",
    "Dublino": "Dublin",
    "Zurigo": "Zurich",
    "Ginevra": "Geneva",
    "Barcellona": "Barcelona",
    "Siviglia": "Seville",
    "Lisbona": "Lisbon",
    "Atene": "Athens",
    "Salonicco": "Thessaloniki",
    "La Valletta": "Valletta",
    # città di partenza italiane (i preset di origins usano il nome locale)
    "Firenze": "Florence",
    "Roma": "Rome",
    "Milano": "Milan",
    "Torino": "Turin",
    "Venezia": "Venice",
    "Napoli": "Naples",
    "Genova": "Genoa",
    "Bari": "Bari",
    "Verona": "Verona",
    "Bergamo": "Bergamo",
    "Pisa": "Pisa",
    "Bologna": "Bologna",
    "Rimini": "Rimini",
    "Pescara": "Pescara",
    "Cagliari": "Cagliari",
    "Catania": "Catania",
    "Palermo": "Palermo",
    "Treviso": "Treviso",
    "Monaco": "Munich",
}


def english(city: str) -> str:
    """Nome inglese della città, se esiste una traduzione."""
    return EN_NAMES.get(city, city)


def as_destinations(names: list[str]) -> list[dict[str, Any]]:
    """Nomi -> parametro `destinations`, scartando quelli sconosciuti."""
    out: list[dict[str, Any]] = []
    for name in names:
        preset = resolve(name)
        if preset is not None:
            out.append(preset.as_destination())
    return out


# Ordine "economico prima": quando l'utente dice "non importa dove", si parte da
# queste. Non è una classifica di prezzo (non la conosciamo senza chiedere), è un
# insieme ragionevole dove il prezzo basso è la norma.
CHEAP_FIRST = [
    "Budapest", "Praga", "Cracovia", "Varsavia", "Bratislava", "Lubiana",
    "Sofia", "Riga", "Vilnius", "Tallinn", "Zagabria", "Belgrado",
    "Bucarest", "Cluj", "Danzica", "Brno", "Porto", "Valencia",
]


def shortlist(limit: int = 8) -> list[CityPreset]:
    """Destinazioni da provare quando la destinazione non conta."""
    out: list[CityPreset] = []
    for name in CHEAP_FIRST:
        preset = resolve(name)
        if preset is not None:
            out.append(preset)
        if len(out) >= max(1, int(limit)):
            break
    return out
