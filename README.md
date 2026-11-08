# tripscout

Find the cheapest complete trip — not the cheapest flight.

A cheap flight is not a cheap trip. You find a €40 fare to Vienna, then discover the
hotel costs €70 more on those exact nights than the week before, so you look for other
dates, and the flight goes up. You switch city and the loop starts again. `tripscout`
prices **flights and hotels together on the same dates**, adds what it costs to reach
each departure airport in the first place, and ranks whole trips by the total.

Then it remembers. Every price it sees goes into a local SQLite cache, so a repeat
search costs almost nothing and you can ask whether a price is high or low for those
dates.

## What it does that a flight search does not

| | |
|---|---|
| **Joint search** | The hotel price for a date window is fetched *before* the flight for that window. Google Flights shows you fares; it does not know your hotel bill. |
| **Ground access per airport** | Each departure airport carries an access cost (train, bus, parking, fuel, return). That is what makes Bologna, Florence and Pisa actually comparable instead of nominally comparable. |
| **Budget-driven pruning** | If the cheapest suitable hotel plus the cheapest possible ground access already breaks your budget, the flight requests for that combination are never made. Exploration is spent where it can still win. |
| **Total-cost ranking** | The answer is one number per option — flight × travellers + stay + access + airport transfer — with the breakdown, so you can see whether a city is expensive because of the flight or the bed. |
| **Local price history** | Every observation is recorded. "Is 144 € good for a Thursday-to-Saturday in Budapest in November?" becomes a question with an answer. |

## Install

```bash
hermes plugins install <owner>/tripscout
hermes plugins enable tripscout
```

Python dependencies are declared in `plugin.yaml` (`fast-flights`, `primp`,
`typing_extensions`) and are prepared by Hermes at install time with your consent.
If they are missing, the plugin still loads and the tools tell you what to install.

No API keys. No account. No browser.

## Tools

### `tripscout_search`

The main one. Give it the airports you can reach, the cities you would consider, and a
date window; it prices the whole grid and returns a ranking.

```jsonc
{
  "origins": [
    {"city": "Bologna", "airports": ["BLQ"], "access_cost": 18},
    {"city": "Florence", "airports": ["FLR"], "access_cost": 12},
    {"city": "Pisa", "airports": ["PSA"], "access_cost": 20}
  ],
  "destinations": [
    {"city": "Vienna", "airports": ["VIE"], "country": "AT", "transfer_cost": 4.5},
    {"city": "Budapest", "airports": ["BUD"], "country": "HU", "transfer_cost": 3.5}
  ],
  "window_start": "2026-11-19",
  "window_end": "2026-11-22",
  "nights_min": 2, "nights_max": 3,
  "weekdays": ["giovedì", "venerdì"],
  "adults": 1, "budget_total": 400, "max_requests": 60
}
```

Returns the best option, a ranked list with the cost breakdown, and the best option
per destination. A real run of exactly the request above:

```text
Budapest (HU)  2026-11-19 → 2026-11-21 (2 notti)  from Pisa PSA   144 EUR
               volo 77 + hotel 40 (Flow Spaces) + adduzione 20 + transfer 7
Vienna (AT)    2026-11-20 → 2026-11-22 (2 notti)  from Bologna BLQ 255 EUR
               volo 156 + hotel 72 (Suburb Hostel) + adduzione 18 + transfer 9
```

`max_requests` is a real budget: the sweep stops when it runs out and says the answer
is partial rather than pretending it finished.

### `tripscout_price_trip`

One exact trip, end to end: cheapest flight for those dates, cheapest hotel for the
same nights, every line of the total, plus the next five hotels as alternatives.

### `tripscout_history`

Reads the local cache only — no network. Price observations for a route or a stay,
the lowest ever seen, and how much is cached.

## Schedules: turn it into a standing search

Point a cronjob at it and let the price history do the work:

```text
Every day at 08:00, run tripscout_search for my usual airports and cities two weekends
out, and message me only if some option's total is below 200 EUR or is lower than any
total recorded so far for that combination.
```

The cache makes the daily version cheap, and `tripscout_history` is what makes "lower
than anything seen so far" a real comparison instead of a guess.

## How the data is fetched

Both sources are Google Travel's public web pages, read over plain HTTPS with a
browser TLS fingerprint (`primp`, Chrome impersonation). No API key is involved, which
is the point: there is no free, open flight-and-hotel API left — Amadeus shut its
self-service tier in July 2026 — and the ones that exist are per-route, per-date, and
priced for businesses.

- **Flights** — Google Flights. `fast-flights` builds the `tfs` query protobuf and
  parses the results page; the transport is this plugin's own, because it must carry
  the consent cookie below.
- **Hotels** — Google Hotels' `batchexecute` RPC (`AtySUc`), implemented here: dates,
  occupancy and currency are encoded in the request, and the response gives the
  **stay total** for the nights asked for, which is the quantity that actually adds to
  the flight.
- **Consent** — in the EU Google answers with the "Before you continue" interstitial
  instead of results. The plugin sends the `SOCS` cookie declaring essential cookies
  only, which is what a rejection of non-essential cookies looks like. It never sends
  a consent value that accepts tracking.

**Disclosure, for the catalog and for you.** Searches send the cities, airports, dates,
traveller count and currency to Google; nothing else about you is included, and no
credential or personal data is ever read, stored or transmitted. Prices, hotel names and
cache keys are stored locally in SQLite under Hermes' own plugin data directory
(`plugin-data/tripscout/`). Nothing is booked and no purchase is ever initiated —
`tripscout` prices and returns links-free numbers, it does not reserve.

## Known limitations

- **The flight price floor is Google's default ranking, not its "cheapest" list.** The
  page contains cheaper fares than the parser extracts on some routes, so a route served
  by low-cost carriers can look more expensive than it is. On many routes the numbers
  are right (the run above prices Pisa→Budapest at 77 € round trip); on some they are
  too high. Treat the flight component as an upper bound and the *ranking*, which
  compares like for like across all options, as the reliable part. Parsing the cheapest
  tab properly is the next piece of work.
- **One request per route and date pair.** Google has no bulk endpoint for this, so a
  wide grid costs a request per cell and is rate-limited by design. The cache and the
  pruning exist precisely because of this; raise `min_interval` if you see blocks.
- **Hotels are the cheapest suitable stay for the dates**, which is the right default
  for "spend little" but is not a hotel you would necessarily want.
- Prices are snapshots, not quotes. Nothing here is bookable state.

## Development

```bash
python tests/test_offline.py        # 10 tests, no network
hermes plugins validate . --install-deps
hermes plugins doctor .
```

The tests cover the date grid, the weekday parsing, the hotel request encoding, the
price extraction, the cache and history, and — the one that matters most — that a
combination whose hotel alone breaks the budget never spends a flight request.

## Licence

MIT.

Prior art: [`viajante`](https://github.com/felipebasurto/viajante) (MIT) demonstrated
that Google Flights and Google Hotels can be read without keys from the user's own
machine. The consent-cookie approach and the position of the hotel price in the
`AtySUc` response were confirmed against its published source; the code here is an
independent implementation of the same public protocol.
