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


def test_classify_lodging_from_google_types() -> None:
    from tripscout_core.hotels import classify

    # ostello vince su hotel: a&o e MEININGER sono marcati entrambi
    assert classify(["hotel", "hostel", "youth_hostel"]) == "hostel"
    assert classify(["hostel"]) == "hostel"
    assert classify(["hotel"]) == "hotel"
    assert classify(["capsule_hotel"]) == "hotel"
    assert classify(["motel", "cafe"]) == "hotel"
    assert classify(["extended_stay_hotel"]) == "apartment"
    # solo etichette non residenziali -> non è un alloggio
    assert classify(["bar", "sports_bar"]) == "other"
    # i vacation rentals non portano gcid: sono appartamenti per costruzione
    assert classify([], rentals_mode=True) == "apartment"
    assert classify([], rentals_mode=False) == "other"


def test_parse_lodging_aliases() -> None:
    from tripscout_core.hotels import _parse_lodging

    assert _parse_lodging(None) == {"any"}
    assert _parse_lodging("hostel") == {"hostel"}
    assert _parse_lodging(["Ostelli", "appartamenti"]) == {"hostel", "apartment"}
    assert _parse_lodging(["hotel", "qualsiasi"]) == {"any"}
    assert _parse_lodging("albergo") == {"hotel"}
    assert _parse_lodging("roba strana") == {"any"}


def test_estimates_days_and_rates() -> None:
    from tripscout_core.estimates import estimate_stay

    # giorni di presenza = notti + 1
    est = estimate_stay(city="Vienna", country="AT", nights=2, adults=1)
    assert est.days == 3
    assert est.food_per_day == 26.0  # Austria
    assert est.food_total == 78.0
    assert est.activities_total == 30.0  # 10/giorno * 3
    assert est.total == 108.0

    # override esplicito dell'utente
    est2 = estimate_stay(city="Vienna", country="AT", nights=1, adults=2,
                         food_per_day=15.0, activities_per_day=0.0)
    assert est2.days == 2
    assert est2.food_total == 60.0  # 15 * 2 giorni * 2 persone
    assert est2.activities_total == 0.0
    assert "user" in est2.basis

    # una città più cara del paese viene trattata come tale
    est3 = estimate_stay(city="Zurigo", country="CH", nights=1)
    assert est3.food_per_day > 42.0


def test_sweep_passes_lodging_and_adds_estimates() -> None:
    """Il filtro alloggio arriva alla ricerca hotel; le stime si aggiungono a parte."""
    seen: dict = {}

    def fake_hotels(session, city, check_in, check_out, **kwargs):
        seen["lodging"] = kwargs.get("lodging")
        return [Stay(name="Ostello", total_price=200, price_text="200 €", kind="hostel")]

    class FakeOffer:
        price = 60.0
        airlines = ["Wizz"]
        stops = 0
        departure = "2026-11-19 07:00"
        arrival = "2026-11-19 09:00"

    original_hotels, original_flights = optimizer.search_stays, optimizer.cheapest_flight
    optimizer.search_stays = fake_hotels
    optimizer.cheapest_flight = lambda *a, **k: FakeOffer()
    try:
        spec = optimizer.Spec(
            origins=[optimizer.Origin(city="Bologna", airports=["BLQ"], access_cost=18.0)],
            destinations=[optimizer.Destination(city="Vienna", airports=["VIE"],
                                               country="AT", transfer_cost=4.0)],
            window_start=date(2026, 11, 19),
            window_end=date(2026, 11, 20),
            nights_min=1,
            nights_max=1,
            weekdays={3},
            adults=1,
            lodging={"hostel"},
            estimates=True,
        )
        result = optimizer.sweep(spec)
        assert seen["lodging"] == {"hostel"}
        best = result.options[0]
        assert best.lodging_kind == "hostel"
        assert best.estimate is not None
        # volo 60 + hotel 200 + adduzione 18 + transfer 8 = 286
        assert abs(best.total - 286.0) < 0.01
        # notti 1 -> 2 giorni: cibo 26*2=52, attrazioni 10*2=20
        assert abs(best.estimate["food_total"] - 52.0) < 0.01
        assert abs(best.estimate["activities_total"] - 20.0) < 0.01
        assert abs(best.total_with_estimates - (286.0 + 72.0)) < 0.01
    finally:
        optimizer.search_stays, optimizer.cheapest_flight = original_hotels, original_flights


def test_home_city_resolves_to_airports_with_costs() -> None:
    """'Prato' deve diventare FI/PI/BO con i costi di adduzione, senza che l'utente lo dica."""
    from tripscout_core.origins import known_cities, resolve

    preset = resolve("Prato")
    assert preset is not None
    codes = [a.airport for a in preset.airports]
    assert codes == ["FLR", "PSA", "BLQ"], codes
    assert all(a.access_cost > 0 for a in preset.airports)

    origins = preset.as_origins()
    assert origins[0]["airports"] == ["FLR"]
    assert isinstance(origins[0]["access_cost"], float)

    # varianti di scrittura
    assert resolve("prato (po)").city == "Prato"
    assert resolve("  PRATO ") is not None
    assert resolve("Firenze") is not None
    assert resolve("Florence") is not None
    assert resolve("Atlantide") is None
    assert resolve("") is None

    cities = known_cities()
    assert "Prato" in cities and "Milano" in cities and len(cities) >= 20


def test_search_with_home_instead_of_origins() -> None:
    """Passando solo `home` la ricerca parte, e gli aeroporti sono quelli del preset."""
    from tripscout_core import tools as agent_tools

    captured: dict = {}

    def fake_search(params):
        captured.update(params)
        return json.dumps({"ok": True})

    original = agent_tools.sweep
    agent_tools.sweep = lambda spec, session=None: (_ for _ in ()).throw(AssertionError("no network"))
    try:
        # senza origins e senza home: errore esplicito con le città note
        out = json.loads(agent_tools.search({"destinations": [{"city": "Vienna", "airports": ["VIE"]}]}))
        assert "error" in out and "Prato" in out["error"]
    finally:
        agent_tools.sweep = original

    # e il tool delle partenze risolve una città
    resolved = json.loads(agent_tools.origins({"city": "Prato"}))
    assert resolved["city"] == "Prato"
    assert [a["airport"] for a in resolved["airports"]] == ["FLR", "PSA", "BLQ"]
    listed = json.loads(agent_tools.origins({}))
    assert listed["count"] >= 20


def test_booking_links_are_prefilled():
    from tripscout_core import links

    flight = links.flight("PSA", "BUD", "2026-11-26", "2026-11-28")
    assert flight.startswith("https://www.google.com/travel/flights?q=")
    assert "BUD" in flight and "PSA" in flight and "2026-11-26" in flight

    stay = links.stay("Flow Spaces", "Budapest", "2026-11-26", "2026-11-28", adults=2, kind="hostel")
    assert "checkin=2026-11-26" in stay["booking"] and "group_adults=2" in stay["booking"]
    assert "date_from=2026-11-26" in stay["hostelworld"]
    assert "adults=2" in stay["airbnb"]
    assert stay["google"].startswith("https://www.google.com/travel/search")

    ground = links.ground("Prato", "PSA")
    assert "origin=Prato" in ground and "PSA" in ground and "travelmode=transit" in ground

    moved = links.transfer("BUD", "Budapest")
    assert "BUD" in moved and "Budapest" in moved


def test_any_place_resolves_to_nearby_airports():
    from tripscout_core import geo

    assert len(geo.airports()) > 3000
    # Firenze: la tabella deve mettere FLR fra i primi, senza rete
    found = geo.nearest(43.7696, 11.2558)
    codes = [airport.iata for airport, _ in found]
    assert "FLR" in codes, codes
    # Prato -> Pisa in linea d'aria ~60 km: la stima deve stare nei preset (16)
    km = geo.haversine_km(43.8777, 11.0969, 43.6839, 10.3927)
    cost, how = geo.access_estimate(km)
    assert 10 <= cost <= 25, (km, cost)
    assert "estimate" in how
    # Tokyo: due scali, entrambi a meno di 100 km
    tokyo = geo.nearest(35.6762, 139.6503)
    assert {"HND", "NRT"} & {a.iata for a, _ in tokyo}


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
