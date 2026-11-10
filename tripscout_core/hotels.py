"""Prezzi hotel da Google Hotels via RPC `batchexecute` (id `AtySUc`).

Nessuna API key e nessun browser: la ricerca per date è un POST JSON.
I prezzi restituiti sono **totali del soggiorno** per le date chieste, che è
esattamente la grandezza da sommare al volo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote, urlencode

from tripscout_core.net import Session

RPC_URL = "https://www.google.com/_/TravelFrontendUi/data/batchexecute"
RPC_ID = "AtySUc"
SEARCH_REFERER = "https://www.google.com/travel/search"
SORT_LOWEST_PRICE = 3
# Google scarta marche/servizi sul totale se questa coda manca.
_REQUEST_META = (1, None, None, None, None, None, 13, None, 0)
_PROPERTY_HOTELS = 1
_PROPERTY_VACATION_RENTALS = 2
# Titoli di stato, non strutture.
NON_PROPERTY_TITLES = frozenset(
    {"closed", "open", "sold out", "unavailable", "no rooms", "fully booked", "chiuso"}
)

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "X-Same-Domain": "1",
    "Origin": "https://www.google.com",
    "Referer": SEARCH_REFERER,
}


@dataclass(slots=True)
class Stay:
    """Una struttura con il prezzo totale del soggiorno per le date chieste."""

    name: str
    total_price: int | None
    price_text: str = ""
    currency: str = "EUR"
    nightly_text: str = ""
    address: str = ""
    kind: str = "other"
    gcids: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.total_price is not None


# Tipi di alloggio che l'utente può chiedere. `any` non filtra.
LODGING_TYPES = ("hotel", "hostel", "apartment", "any")

# Da `gcid:` di Google alla nostra categoria. L'ordine conta: una struttura
# marcata sia `hotel` sia `hostel` (a&o, MEININGER) è un ostello.
_HOSTEL_GCID = {"hostel", "youth_hostel"}
_APARTMENT_GCID = {
    "apartment_building",
    "apartment_complex",
    "vacation_rental",
    "guest_house",
    "extended_stay_hotel",
    "serviced_accommodation",
}
_HOTEL_GCID = {"hotel", "motel", "resort_hotel", "capsule_hotel", "inn", "lodging"}
# Etichette che non descrivono un alloggio: se sono le uniche, il record va scartato.
_NOT_LODGING_GCID = {"bar", "sports_bar", "cafe", "restaurant", "event_venue", "night_club"}


def _gcids(record: list) -> list[str]:
    """Tutti i `gcid:` del record (Google li annida variamente)."""
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            if node.startswith("gcid:"):
                found.append(node[5:])
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)

    walk(record)
    return found


def classify(gcids: list[str], *, rentals_mode: bool = False) -> str:
    """hotel | hostel | apartment | other.

    I risultati della modalità "vacation rentals" non portano `gcid`: sono
    appartamenti e stanze private per costruzione.
    """
    if not gcids:
        return "apartment" if rentals_mode else "other"
    present = set(gcids)
    if present & _HOSTEL_GCID:
        return "hostel"
    if present & _APARTMENT_GCID:
        return "apartment"
    if present & _HOTEL_GCID:
        return "hotel"
    if present and present <= _NOT_LODGING_GCID:
        return "other"
    return "other"


def _dates_slot(check_in: date, check_out: date) -> list:
    nights = (check_out - check_in).days
    return [
        None,
        [
            [check_in.year, check_in.month, check_in.day],
            [check_out.year, check_out.month, check_out.day],
            nights,
        ],
        None,
        None,
        None,
        [None, 0],
    ]


def build_request(
    location: str,
    check_in: date,
    check_out: date,
    *,
    currency: str = "EUR",
    language: str = "it",
    adults: int = 2,
    rooms: int = 1,
    entire_home: bool = False,
    free_cancellation: bool = False,
) -> tuple[str, str]:
    """(url, body) della ricerca hotel. Le date sono [anno, mese, giorno]."""
    extras = None
    if adults != 2 or rooms != 1:
        # L'occupancy di default di Google è 2 adulti / 1 camera.
        extras = [[[3]] * adults, rooms]
    filters = [
        None,
        None,
        None,
        1 if free_cancellation else None,
        SORT_LOWEST_PRICE,
        None,
        currency,
        None,
    ]
    search_params = [
        _PROPERTY_VACATION_RENTALS if entire_home else _PROPERTY_HOTELS,
        extras,
        [None, _dates_slot(check_in, check_out)],
        None,
        [filters, None, [], [None, None, 1]],
    ]
    inner = json.dumps(
        [f"{location} hotels", search_params, list(_REQUEST_META)], separators=(",", ":")
    )
    envelope = [[[RPC_ID, inner, None, "1"]]]
    body = "f.req=" + quote(json.dumps(envelope, separators=(",", ":")), safe="")
    url = RPC_URL + "?" + urlencode(
        {
            "hl": language,
            "curr": currency,
            "soc-app": "162",
            "soc-platform": "1",
            "soc-device": "1",
            "rt": "c",
        }
    )
    return url, body


def wrb_payloads(text: str) -> list:
    """Payload JSON dei chunk `wrb.fr`, con o senza prefisso di lunghezza."""
    payloads: list = []
    chunks = re.split(r"\n\d+\n", text)
    if len(chunks) == 1 and "\n" in text:
        chunks = text.split("\n")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or chunk.startswith(")]}'"):
            chunk = chunk[4:].strip() if chunk.startswith(")]}'") else chunk
        if not chunk.startswith("["):
            continue
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        rows = obj if (obj and isinstance(obj[0], list)) else [obj]
        for row in rows:
            if isinstance(row, list) and len(row) >= 3 and row[0] == "wrb.fr":
                if isinstance(row[2], str):
                    try:
                        payloads.append(json.loads(row[2]))
                    except json.JSONDecodeError:
                        pass
    return payloads


def _stay_total(record: list) -> str | None:
    """Prezzo totale del soggiorno: `record[6][2][9]`, coppia `[?, totale]` o `[totale]`."""
    try:
        pair = record[6][2][9]
    except (IndexError, KeyError, TypeError):
        return None
    if not isinstance(pair, list) or not pair:
        return None
    # In una coppia il primo elemento è una cifra "per notte": non deve mai
    # sostituire il totale. Solo una lista di un elemento è un totale nudo.
    candidates = [pair[0]] if len(pair) == 1 else [pair[1]]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate and any(c.isdigit() for c in candidate):
            return candidate
    return None


def _nightly(record: list) -> str:
    try:
        pair = record[6][2][1]
    except (IndexError, KeyError, TypeError):
        return ""
    if isinstance(pair, list) and pair and isinstance(pair[0], str):
        return pair[0]
    return ""


def _address(record: list) -> str:
    try:
        value = record[6][1][2]
    except (IndexError, KeyError, TypeError):
        return ""
    return value if isinstance(value, str) else ""


def to_number(text: str | None) -> int | None:
    """'1.234 €' -> 1234. None se non c'è una cifra."""
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def _collect(obj, found: list) -> None:
    """Record struttura = lista lunga con titolo stringa e un prezzo di soggiorno."""
    if (
        isinstance(obj, list)
        and len(obj) >= 8
        and isinstance(obj[1], str)
        and obj[1].strip()
        and obj[1].strip().casefold() not in NON_PROPERTY_TITLES
        and (_stay_total(obj) or _nightly(obj))
    ):
        found.append(obj)
        return
    if isinstance(obj, list):
        for item in obj:
            _collect(item, found)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect(value, found)


def parse_stays(text: str, *, currency: str = "EUR", rentals_mode: bool = False) -> list[Stay]:
    if "unusual traffic" in text.casefold() or "/sorry/" in text.casefold():
        from tripscout_core.net import GoogleBlocked

        raise GoogleBlocked("Google Hotels blocked the request")
    records: list = []
    for payload in wrb_payloads(text):
        _collect(payload, records)
    stays: list[Stay] = []
    for record in records:
        total = _stay_total(record)
        name = record[1].strip()
        gcids = _gcids(record)
        stays.append(
            Stay(
                name=name,
                total_price=to_number(total),
                price_text=total or "",
                currency=currency,
                nightly_text=_nightly(record),
                address=_address(record),
                kind=classify(gcids, rentals_mode=rentals_mode),
                gcids=gcids,
            )
        )
    stays.sort(key=lambda s: (s.total_price is None, s.total_price or 0))
    return stays


def _parse_lodging(lodging) -> set[str]:
    """Normalizza la richiesta dell'utente in un set di categorie."""
    if not lodging:
        return {"any"}
    if isinstance(lodging, str):
        lodging = [lodging]
    wanted: set[str] = set()
    for value in lodging:
        key = str(value).strip().casefold()
        if key in ("any", "all", "tutti", "qualsiasi", "indifferente"):
            return {"any"}
        if key in ("apartment", "apartments", "appartamento", "appartamenti",
                   "flat", "rental", "vacation_rental", "casa"):
            wanted.add("apartment")
        elif key in ("hostel", "hostels", "ostello", "ostelli"):
            wanted.add("hostel")
        elif key in ("hotel", "hotels", "albergo", "alberghi", "b&b"):
            wanted.add("hotel")
    return wanted or {"any"}


def search_stays(
    session: Session,
    location: str,
    check_in: date,
    check_out: date,
    *,
    lodging=None,
    **kwargs,
) -> list[Stay]:
    """Strutture per `location` e quelle date, dalla più economica.

    Gli hotel e gli ostelli arrivano dalla stessa ricerca; gli appartamenti da
    una seconda ricerca (Google li espone come "vacation rentals"), quindi
    chiederli costa una richiesta in più per città e data.
    """
    wanted = _parse_lodging(lodging)
    currency = kwargs.get("currency", "EUR")
    kwargs.pop("entire_home", None)
    want_serviced = "any" in wanted or bool(wanted & {"hotel", "hostel"})
    want_apartments = "any" in wanted or "apartment" in wanted

    stays: list[Stay] = []
    if want_serviced:
        url, body = build_request(location, check_in, check_out, entire_home=False, **kwargs)
        stays.extend(
            parse_stays(
                session.post(url, body=body, headers=HEADERS).text,
                currency=currency,
                rentals_mode=False,
            )
        )
    if want_apartments:
        url, body = build_request(location, check_in, check_out, entire_home=True, **kwargs)
        stays.extend(
            parse_stays(
                session.post(url, body=body, headers=HEADERS).text,
                currency=currency,
                rentals_mode=True,
            )
        )

    allowed = None if "any" in wanted else wanted
    usable = [
        stay
        for stay in stays
        if stay.usable and (allowed is None or stay.kind in allowed)
    ]
    usable.sort(key=lambda stay: stay.total_price or 0)
    return usable
