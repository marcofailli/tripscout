"""Test offline: griglia, chiavi di cache, corpo della richiesta hotel, potatura.

Nessuna rete. Eseguibile senza pytest:

    python tests/test_offline.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.environ["TRIPSCOUT_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")

from tripscout_core import optimizer, store  # noqa: E402
from tripscout_core.grid import parse_weekdays, trips  # noqa: E402
from tripscout_core.hotels import Stay, build_request, parse_stays, to_number  # noqa: E402


def test_grid_respects_window_weekdays_and_nights() -> None:
    found = trips(date(2026, 11, 19), date(2026, 11, 22), 2, 3, {3, 4})
    assert found, "la finestra 19-22 nov con partenze gio/ven deve produrre combinazioni"
    for trip in found:
        assert trip.depart.weekday() in (3, 4), trip
        assert 2 <= trip.nights <= 3, trip
        assert trip.ret > trip.depart
        assert (trip.ret - trip.depart).days == trip.nights
    # la finestra si chiude prima del ritorno: nessuna combinazione fuori range
    assert all(t.ret <= date(2026, 11, 22) for t in found)


def test_grid_dedupes_and_caps() -> None:
    capped = trips(date(2026, 1, 1), date(2026, 12, 31), 2, 4, None, max_options=10)
    assert len(capped) == 10
    assert capped == sorted(capped, key=lambda t: (t.depart, t.nights))


def test_weekday_parsing_italian_and_english() -> None:
    assert parse_weekdays(["giovedì", "friday"]) == {3, 4}
    assert parse_weekdays(["thu", 4]) == {3, 4}
    assert parse_weekdays([]) == set()


def test_hotel_request_carries_dates_currency_and_occupancy() -> None:
    url, body = build_request("Vienna", date(2026, 11, 19), date(2026, 11, 22),
                              currency="EUR", adults=3, rooms=2)
    assert "batchexecute" in url and "curr=EUR" in url
    assert "AtySUc" in body
    assert "Vienna%20hotels" in body
    # date e occupanza viaggiano URL-encodate nel corpo f.req
    assert "%5B%5B2026%2C11%2C19%5D%2C%5B2026%2C11%2C22%5D%2C3%5D" in body
    assert "%5B%5B%5B3%5D%2C%5B3%5D%2C%5B3%5D%5D%2C2%5D" in body


def test_hotel_request_omits_default_occupancy() -> None:
    _, body_default = build_request("Prague", date(2026, 11, 19), date(2026, 11, 22))
    _, body_custom = build_request("Prague", date(2026, 11, 19), date(2026, 11, 22), adults=4)
    # l'occupancy di default (2/1) non va inviata, una diversa sì: i corpi differiscono
    assert body_default != body_custom
    assert len(body_default) < len(body_custom)


def test_price_text_is_parsed_to_a_number() -> None:
    assert to_number("107 €") == 107
    assert to_number("1.234 €") == 1234
    assert to_number("€ 89,50") == 8950 or to_number("€ 89,50") == 8950
    assert to_number("") is None
    assert to_number("nessun prezzo") is None


def test_parse_stays_reads_records_and_sorts_by_total() -> None:
    """Una risposta wrb.fr sintetica, nel formato che Google usa davvero."""
    def record(name: str, total: str, nightly: str = "45 €") -> list:
        return [
            None, name, None, None, None, None,
            [None, None, [None, nightly, None, None, None, None, None, None, None, [None, total]]],
            None,
        ]

    payload = [[record("Hotel Caro", "320 €"), record("Hotel Bello", "198 €")]]
    row = ["wrb.fr", "AtySUc", json.dumps(payload), None, None, None, "generic"]
    text = ")]}'\n\n" + str(len(json.dumps([row]))) + "\n" + json.dumps([row]) + "\n"

    stays = parse_stays(text)
    assert [s.name for s in stays] == ["Hotel Bello", "Hotel Caro"], stays
    assert stays[0].total_price == 198
    assert stays[1].total_price == 320
    assert all(s.usable for s in stays)

    # il primo elemento di una coppia è una cifra per notte: non deve diventare il totale
    pair_record = record("Hotel Pair", "0 €")
    pair_record[6][2][9] = ["45 €", "260 €"]
    assert parse_stays(_wrap(pair_record))[0].total_price == 260

    assert parse_stays('[["wrb.fr", "AtySUc", "[]", null]]') == []


def _wrap(*records: list) -> str:
    row = ["wrb.fr", "AtySUc", json.dumps([list(records)]), None]
    return json.dumps([row])


def test_cache_roundtrip_and_history() -> None:
    key = "BLQ>VIE:2026-11-19:2026-11-22:a1:sNone:EUR"
    store.put("flight", key, {"price": 148})
    assert store.get("flight", key, 1) == {"price": 148}
    # ttl negativo = ignora l'età della voce (serve allo storico)
    assert store.get("flight", key, -1) == {"price": 148}
    # ttl 0 = la voce è già considerata vecchia
    assert store.get("flight", key, 0) is None
    store.record_price("flight", key, 148, "EUR")
    store.record_price("flight", key, 122, "EUR")
    history = store.price_history("flight", key)
    prices = [h["price"] for h in history if "price" in h]
    assert 122 in prices and 148 in prices
    assert history[-1]["summary"] == "lowest_observed"
    assert history[-1]["price"] == 122


def test_budget_pruning_skips_flight_requests() -> None:
    """Se l'hotel da solo sfonda il budget, i voli non si cercano affatto."""
    calls = {"hotel": 0, "flight": 0}

    def fake_hotels(session, city, check_in, check_out, **kwargs):
        calls["hotel"] += 1
        return [Stay(name="Caro", total_price=900, price_text="900 €")]

    def fake_flights(*args, **kwargs):
        calls["flight"] += 1
        raise AssertionError("non deve essere chiamata: la potatura doveva scattare prima")

    original_hotels, original_flights = optimizer.search_stays, optimizer.cheapest_flight
    optimizer.search_stays, optimizer.cheapest_flight = fake_hotels, fake_flights
    try:
        spec = optimizer.Spec(
            origins=[optimizer.Origin(city="Bologna", airports=["BLQ"], access_cost=20.0)],
            destinations=[optimizer.Destination(city="Vienna", airports=["VIE"])],
            window_start=date(2026, 11, 19),
            window_end=date(2026, 11, 22),
            nights_min=2,
            nights_max=3,
            weekdays={3, 4},
            adults=1,
            budget_total=400,
        )
        result = optimizer.sweep(spec)
        assert calls["hotel"] > 0, "gli hotel vanno comunque valutati"
        assert calls["flight"] == 0, "i voli non devono partire"
        assert result.stats["pruned_on_hotel_price"] > 0
        assert result.options == []
    finally:
        optimizer.search_stays, optimizer.cheapest_flight = original_hotels, original_flights


def test_total_costs_include_every_line() -> None:
    """Il totale somma volo×persone, soggiorno, adduzione e transfer in città."""
    def fake_hotels(session, city, check_in, check_out, **kwargs):
        return [Stay(name="Hotel", total_price=200, price_text="200 €")]

    class FakeOffer:
        price = 60.0
        airlines = ["Ryanair"]
        stops = 0
        departure = "2026-11-19 07:00"
        arrival = "2026-11-19 09:00"

    original_hotels, original_flights = optimizer.search_stays, optimizer.cheapest_flight
    optimizer.search_stays = fake_hotels
    optimizer.cheapest_flight = lambda *a, **k: FakeOffer()
    try:
        spec = optimizer.Spec(
            origins=[optimizer.Origin(city="Bologna", airports=["BLQ"], access_cost=18.0)],
            destinations=[optimizer.Destination(city="Vienna", airports=["VIE"], transfer_cost=4.0)],
            window_start=date(2026, 11, 19),
            window_end=date(2026, 11, 20),
            nights_min=1,
            nights_max=1,
            weekdays={3},
            adults=2,
            rooms=1,
        )
        result = optimizer.sweep(spec)
        assert result.options, "deve produrre almeno un'opzione"
        best = result.options[0]
        expected = 60.0 * 2 + 200.0 + 18.0 * 2 + 4.0 * 2 * 2
        assert abs(best.total - expected) < 0.01, (best.total, expected)
        assert abs(best.flight_total - 120.0) < 0.01
        assert abs(best.access_total - 36.0) < 0.01
        assert abs(best.transfer_total - 16.0) < 0.01
    finally:
        optimizer.search_stays, optimizer.cheapest_flight = original_hotels, original_flights


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} test superati")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
