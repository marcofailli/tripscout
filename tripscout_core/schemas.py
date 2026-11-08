"""Schemi dei tool: è questo testo che il modello legge per decidere quando usarli."""

from __future__ import annotations

_ORIGIN = {
    "type": "object",
    "description": "Aeroporto di partenza che l'utente può raggiungere.",
    "properties": {
        "city": {"type": "string", "description": "Città dell'aeroporto, es. 'Firenze'."},
        "airports": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Codici IATA, es. ['FLR'].",
        },
        "access_cost": {
            "type": "number",
            "description": (
                "Costo a persona per raggiungere questo aeroporto e tornare, "
                "nella valuta scelta. Include treno, bus, parcheggio o benzina: "
                "è la voce che rende confrontabili aeroporti diversi."
            ),
        },
    },
    "required": ["city", "airports"],
}

_DESTINATION = {
    "type": "object",
    "description": "Città candidata per il soggiorno.",
    "properties": {
        "city": {
            "type": "string",
            "description": "Nome della città come lo cerca un motore di ricerca, es. 'Vienna'.",
        },
        "airports": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Aeroporti della città, es. ['VIE'] o ['BUD'].",
        },
        "country": {"type": "string", "description": "Paese, facoltativo (es. 'AT')."},
        "transfer_cost": {
            "type": "number",
            "description": "Costo a persona, a tratta, aeroporto↔centro città.",
        },
    },
    "required": ["city", "airports"],
}

_COMMON = {
    "adults": {"type": "integer", "description": "Viaggiatori adulti. Default 1."},
    "rooms": {"type": "integer", "description": "Camere d'hotel. Default 1."},
    "currency": {"type": "string", "description": "Valuta dei prezzi. Default 'EUR'."},
    "language": {"type": "string", "description": "Lingua delle interfacce interrogate. Default 'it'."},
    "max_requests": {
        "type": "integer",
        "description": (
            "Tetto di richieste di rete per questa ricerca. Default 80. "
            "Se finisce, la risposta è parziale e lo dichiara."
        ),
    },
    "min_interval": {
        "type": "number",
        "description": "Secondi minimi fra due richieste. Alzalo se compare un blocco. Default 1.0.",
    },
    "cache_ttl_hours": {
        "type": "number",
        "description": "Validità della cache dei prezzi, in ore. Default 12.",
    },
}

SEARCH = {
    "name": "tripscout_search",
    "description": (
        "Find the cheapest complete trip (flight + hotel + getting to the airport) over a date "
        "window and several candidate cities, and rank whole trips by total cost. Use this when "
        "someone asks where and when to go cheaply and is flexible about the destination: it "
        "searches flights and hotels TOGETHER on the same dates, instead of pricing a flight and "
        "then discovering the hotel costs more on those nights. Prices a whole grid, caches every "
        "result in SQLite so a repeat search is nearly free, and prunes combinations whose hotel "
        "alone already breaks the budget. Returns a ranked list with the cost breakdown for each "
        "option, so the answer is 'go here, these dates, this total', not a wall of flights."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origins": {
                "type": "array",
                "items": _ORIGIN,
                "description": "Aeroporti di partenza considerati, tutti confrontati fra loro.",
            },
            "destinations": {
                "type": "array",
                "items": _DESTINATION,
                "description": "Città candidate. Tienile fra 4 e 12: ognuna costa richieste.",
            },
            "window_start": {
                "type": "string",
                "description": "Prima data di partenza, YYYY-MM-DD. Omettila per usare i prossimi weekend.",
            },
            "window_end": {
                "type": "string",
                "description": "Ultima data entro cui si deve rientrare, YYYY-MM-DD.",
            },
            "weekends": {
                "type": "integer",
                "description": (
                    "Se non dai le date: quanti weekend (giovedì→domenica) esplorare da qui. "
                    "Default 2."
                ),
            },
            "nights_min": {"type": "integer", "description": "Notti minime. Default 2."},
            "nights_max": {"type": "integer", "description": "Notti massime. Default 4."},
            "weekdays": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Giorni di partenza ammessi, nomi inglesi o italiani: ['thursday','friday'] "
                    "oppure ['giovedì','venerdì']. Default giovedì e venerdì."
                ),
            },
            "budget_total": {
                "type": "number",
                "description": (
                    "Tetto di spesa per l'intero viaggio, per il gruppo indicato. "
                    "Le combinazioni che lo sfondano solo con l'hotel non vengono nemmeno cercate."
                ),
            },
            "top": {"type": "integer", "description": "Quante opzioni restituire. Default 10."},
            "max_stops": {"type": "integer", "description": "Scali massimi per tratta. 0 = solo diretti."},
            **_COMMON,
        },
        "required": ["origins", "destinations"],
    },
}

PRICE_TRIP = {
    "name": "tripscout_price_trip",
    "description": (
        "Price one exact trip end to end: the cheapest flight for those dates, the cheapest hotel "
        "for the same nights, ground access to the departure airport and the transfer into town, "
        "with the total and every line of the breakdown. Use it to confirm or detail a single "
        "option that tripscout_search already surfaced, or when the user has already chosen city "
        "and dates and wants to know what it really costs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "origin_airport": {"type": "string", "description": "IATA di partenza, es. 'BLQ'."},
            "origin_city": {"type": "string", "description": "Città di partenza, solo per leggibilità."},
            "access_cost": {
                "type": "number",
                "description": "Costo a persona per raggiungere l'aeroporto e tornare.",
            },
            "dest_city": {"type": "string", "description": "Città di destinazione, es. 'Vienna'."},
            "dest_airport": {"type": "string", "description": "IATA di arrivo, es. 'VIE'."},
            "transfer_cost": {
                "type": "number",
                "description": "Costo a persona, a tratta, aeroporto↔centro.",
            },
            "depart": {"type": "string", "description": "Data di andata, YYYY-MM-DD."},
            "ret": {"type": "string", "description": "Data di ritorno, YYYY-MM-DD."},
            "max_stops": {"type": "integer", "description": "Scali massimi per tratta."},
            **_COMMON,
        },
        "required": ["origin_airport", "dest_city", "dest_airport", "depart", "ret"],
    },
}

HISTORY = {
    "name": "tripscout_history",
    "description": (
        "Show the price history tripscout has recorded for one route or one stay, plus the lowest "
        "price ever observed and the cache inventory. Use it to answer 'is this cheap for these "
        "dates?' or 'what did we see before?' without spending new requests. Reads only the local "
        "SQLite cache."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["flight", "hotel", "all"],
                "description": "Cosa interrogare. Default 'all' (inventario della cache).",
            },
            "origin_airport": {"type": "string", "description": "IATA di partenza, per i voli."},
            "dest_airport": {"type": "string", "description": "IATA di arrivo, per i voli."},
            "dest_city": {"type": "string", "description": "Città del soggiorno, per gli hotel."},
            "depart": {"type": "string", "description": "Data di andata, YYYY-MM-DD."},
            "ret": {"type": "string", "description": "Data di ritorno, YYYY-MM-DD."},
            "limit": {"type": "integer", "description": "Quante osservazioni restituire. Default 20."},
            **_COMMON,
        },
        "required": [],
    },
}
