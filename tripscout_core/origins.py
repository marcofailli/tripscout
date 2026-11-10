"""Partenze per città: "parto da Prato" -> FI / PI / BO con i costi di adduzione.

Questi sono i costi per raggiungere l'aeroporto e tornare, a persona: treno,
bus, metro o navetta. Sono stime dichiarate, pensate per un viaggio economico,
e chiunque può sovrascriverle passando `origins` espliciti.

La tabella copre le città italiane servite da più aeroporti (dove la scelta
dell'aeroporto cambia davvero il prezzo del viaggio) e alcune europee. Non è
un database di trasporti: è il pezzo che evita all'utente di dover sapere che
da Prato conviene guardare Firenze, Pisa e Bologna insieme.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class AirportAccess:
    airport: str          # IATA
    airport_city: str     # città dell'aeroporto
    access_cost: float    # EUR a persona, andata e ritorno
    how: str              # come ci si arriva, in breve

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HomePreset:
    city: str
    region: str
    airports: list[AirportAccess]

    def as_origins(self) -> list[dict[str, Any]]:
        """Formato pronto per il parametro `origins` dei tool."""
        return [
            {
                "city": a.airport_city,
                "airports": [a.airport],
                "access_cost": a.access_cost,
            }
            for a in self.airports
        ]


def _p(airport: str, city: str, cost: float, how: str) -> AirportAccess:
    return AirportAccess(airport=airport, airport_city=city, access_cost=cost, how=how)


# Chiavi: nome della città in minuscolo (con e senza accento dove serve).
PRESETS: dict[str, HomePreset] = {}


def _add(city: str, region: str, airports: list[AirportAccess], *aliases: str) -> None:
    preset = HomePreset(city=city, region=region, airports=airports)
    for key in (city.casefold(), *(alias.casefold() for alias in aliases)):
        PRESETS[key] = preset


# --- Toscana ---------------------------------------------------------------
_add("Prato", "Toscana", [
    _p("FLR", "Firenze", 9.0, "treno Prato→Firenze SMN + tramvia T2"),
    _p("PSA", "Pisa", 16.0, "treno regionale diretto + people mover"),
    _p("BLQ", "Bologna", 24.0, "treno via Firenze + Marconi Express"),
], "prato (po)")
_add("Firenze", "Toscana", [
    _p("FLR", "Firenze", 6.0, "tramvia T2 da Santa Maria Novella"),
    _p("PSA", "Pisa", 18.0, "treno regionale + people mover"),
    _p("BLQ", "Bologna", 26.0, "treno AV + Marconi Express"),
], "florence")
_add("Pisa", "Toscana", [
    _p("PSA", "Pisa", 5.0, "people mover dalla stazione"),
    _p("FLR", "Firenze", 16.0, "treno + tramvia T2"),
], "pisa centrale")
_add("Siena", "Toscana", [
    _p("FLR", "Firenze", 18.0, "rapida Siena→Firenze + tramvia"),
    _p("PSA", "Pisa", 20.0, "treno via Empoli + people mover"),
])
_add("Arezzo", "Toscana", [
    _p("FLR", "Firenze", 16.0, "treno regionale + tramvia T2"),
    _p("PGO", "Perugia", 22.0, "treno + bus"),
])
_add("Livorno", "Toscana", [
    _p("PSA", "Pisa", 8.0, "treno regionale + people mover"),
    _p("FLR", "Firenze", 22.0, "treno + tramvia"),
])
_add("Lucca", "Toscana", [
    _p("PSA", "Pisa", 7.0, "treno + people mover"),
    _p("FLR", "Firenze", 20.0, "treno + tramvia"),
])

# --- Emilia-Romagna --------------------------------------------------------
_add("Bologna", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 11.0, "Marconi Express dal centro"),
    _p("FLR", "Firenze", 28.0, "treno AV + tramvia T2"),
], "bologna centrale")
_add("Modena", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 16.0, "treno + Marconi Express"),
    _p("VRN", "Verona", 26.0, "treno + bus"),
])
_add("Parma", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 18.0, "treno + Marconi Express"),
    _p("BGY", "Bergamo", 28.0, "treno + bus navetta"),
    _p("VRN", "Verona", 24.0, "treno + bus"),
])
_add("Reggio Emilia", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 16.0, "treno + Marconi Express"),
    _p("BGY", "Bergamo", 30.0, "treno + navetta"),
], "reggio nell'emilia")
_add("Rimini", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 20.0, "treno + Marconi Express"),
    _p("RMI", "Rimini", 6.0, "bus 9 dal centro"),
])
_add("Ravenna", "Emilia-Romagna", [
    _p("BLQ", "Bologna", 18.0, "treno + Marconi Express"),
    _p("RMI", "Rimini", 22.0, "treno + bus"),
])

# --- Nord ----------------------------------------------------------------
_add("Milano", "Lombardia", [
    _p("LIN", "Milano", 6.0, "metro M4 / bus 73"),
    _p("MXP", "Milano", 26.0, "Malpensa Express"),
    _p("BGY", "Bergamo", 14.0, "bus navetta da Centrale"),
], "milan")
_add("Bergamo", "Lombardia", [
    _p("BGY", "Bergamo", 7.0, "bus 1 / navetta"),
    _p("LIN", "Milano", 24.0, "treno + metro"),
])
_add("Brescia", "Lombardia", [
    _p("BGY", "Bergamo", 14.0, "treno + bus 1"),
    _p("VRN", "Verona", 18.0, "treno + bus navetta"),
])
_add("Torino", "Piemonte", [
    _p("TRN", "Torino", 10.0, "treno GTT / bus Sadem"),
    _p("MXP", "Milano", 30.0, "treno + Malpensa Express"),
], "turin")
_add("Genova", "Liguria", [
    _p("GOA", "Genova", 8.0, "volabus dal centro"),
    _p("MXP", "Milano", 34.0, "treno + Malpensa Express"),
], "genoa")
_add("Venezia", "Veneto", [
    _p("VCE", "Venezia", 16.0, "bus 5 aerobus / treno Mestre"),
    _p("VRN", "Verona", 26.0, "treno + bus navetta"),
], "venice")
_add("Verona", "Veneto", [
    _p("VRN", "Verona", 12.0, "aerobus da Porta Nuova"),
    _p("VCE", "Venezia", 28.0, "treno + aerobus"),
])
_add("Trieste", "Friuli-Venezia Giulia", [
    _p("TRS", "Trieste", 8.0, "bus E51 / treno"),
    _p("VCE", "Venezia", 34.0, "treno + aerobus"),
])
_add("Bolzano", "Trentino-Alto Adige", [
    _p("VRN", "Verona", 22.0, "treno + aerobus"),
    _p("BGY", "Bergamo", 34.0, "treno + navetta"),
])

# --- Centro e Sud --------------------------------------------------------
_add("Roma", "Lazio", [
    _p("FCO", "Roma", 18.0, "Leonardo Express / bus Terravision"),
    _p("CIA", "Roma", 12.0, "bus Terravision / treno + bus"),
], "rome")
_add("Perugia", "Umbria", [
    _p("PGO", "Perugia", 10.0, "bus / people mover"),
    _p("FLR", "Firenze", 26.0, "treno + tramvia"),
])
_add("Ancona", "Marche", [
    _p("AOI", "Ancona", 10.0, "bus 12 / treno"),
    _p("BLQ", "Bologna", 30.0, "treno + Marconi Express"),
])
_add("Napoli", "Campania", [
    _p("NAP", "Napoli", 10.0, "Alibus / metro + bus"),
    _p("FCO", "Roma", 36.0, "treno AV + Leonardo Express"),
], "naples")
_add("Bari", "Puglia", [
    _p("BRI", "Bari", 9.0, "treno metropolitano / bus 16"),
    _p("NAP", "Napoli", 34.0, "bus / treno + Alibus"),
])
_add("Brindisi", "Puglia", [
    _p("BDS", "Brindisi", 8.0, "bus STP / treno"),
    _p("BRI", "Bari", 26.0, "treno + bus 16"),
])
_add("Palermo", "Sicilia", [
    _p("PMO", "Palermo", 12.0, "Préstia e Comandé / treno"),
    _p("CTA", "Catania", 30.0, "bus SAIS"),
])
_add("Catania", "Sicilia", [
    _p("CTA", "Catania", 8.0, "Alibus / metro"),
    _p("PMO", "Palermo", 30.0, "bus SAIS"),
])
_add("Cagliari", "Sardegna", [
    _p("CAG", "Cagliari", 8.0, "treno / bus 747"),
])

# --- Fuori Italia (per generalità) ---------------------------------------
_add("Zurigo", "Svizzera", [
    _p("ZRH", "Zurigo", 14.0, "treno SBB dal centro"),
    _p("BSL", "Basilea", 40.0, "treno IC"),
], "zurich")
_add("Monaco", "Germania", [
    _p("MUC", "Monaco", 24.0, "S-Bahn S1/S8"),
    _p("MEM", "Memmingen", 34.0, "bus navetta"),
], "munich", "muenchen")


def resolve(name: str | None) -> HomePreset | None:
    """Città di partenza -> preset, o None se non è in tabella."""
    if not name:
        return None
    key = " ".join(str(name).strip().casefold().split())
    if key in PRESETS:
        return PRESETS[key]
    # "Prato (PO)", "prato po", "Firenze, Toscana"
    head = key.replace(",", " ").split("(")[0].strip()
    if head in PRESETS:
        return PRESETS[head]
    for alias, preset in PRESETS.items():
        if key.startswith(alias) or alias.startswith(head):
            return preset
    return None


def resolve_any(place: str | None) -> HomePreset | None:
    """Preset scritto a mano se esiste, altrimenti geocoding + aeroporti vicini.

    È il pezzo che rende la partenza libera: "Agerola" o "Reykjavik" funzionano
    come "Prato", solo che i costi di adduzione diventano stime sulla distanza.
    """
    preset = resolve(place)
    if preset is not None:
        return preset
    if not place or not str(place).strip():
        return None
    from tripscout_core import geo

    found = geo.resolve(str(place))
    if not found:
        return None
    return HomePreset(
        city=found["city"],
        region="geocoded",
        airports=[
            _p(item["airport"], item["airport_city"], item["access_cost"], item["how"])
            for item in found["airports"]
        ],
    )


def known_cities() -> list[str]:
    """Elenco ordinato delle città di partenza supportate (senza alias)."""
    seen: dict[str, HomePreset] = {}
    for preset in PRESETS.values():
        seen.setdefault(preset.city, preset)
    return sorted(seen)
