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

    @property
    def usable(self) -> bool:
        return self.total_price is not None


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


def parse_stays(text: str, *, currency: str = "EUR") -> list[Stay]:
    if "unusual traffic" in text.casefold() or "/sorry/" in text.casefold():
        from tripscout_core.net import GoogleBlocked

        raise GoogleBlocked("Google Hotels ha bloccato la richiesta")
    records: list = []
    for payload in wrb_payloads(text):
        _collect(payload, records)
    stays: list[Stay] = []
    for record in records:
        total = _stay_total(record)
        name = record[1].strip()
        stays.append(
            Stay(
                name=name,
                total_price=to_number(total),
                price_text=total or "",
                currency=currency,
                nightly_text=_nightly(record),
                address=_address(record),
            )
        )
    stays.sort(key=lambda s: (s.total_price is None, s.total_price or 0))
    return stays


def search_stays(
    session: Session,
    location: str,
    check_in: date,
    check_out: date,
    **kwargs,
) -> list[Stay]:
    """Strutture per `location` e quelle date, dalla più economica."""
    currency = kwargs.get("currency", "EUR")
    url, body = build_request(location, check_in, check_out, **kwargs)
    return parse_stays(session.post(url, body=body, headers=HEADERS).text, currency=currency)
