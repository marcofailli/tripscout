"""Stime indicative di cibo e attrazioni, per città e per giorno.

Sono **stime**, non prezzi: servono a non confrontare un volo a 77 € con un
hotel a 40 € e poi scoprire sul posto che mangiare costa il doppio del previsto.
Chi le usa deve poterle spegnere o sovrascrivere.

I livelli di spesa sono a persona e per giorno, con una spesa "da viaggio
economico": colazione e pranzo al bar/supermercato, una cena semplice, un
biglietto di un'attrazione al giorno. Non includono alcolici, taxi né musei
costosi.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

# Paese (ISO-2) -> cibo a persona al giorno, in EUR. Indicativo.
FOOD_BY_COUNTRY: dict[str, float] = {
    "AT": 26.0,
    "BE": 32.0,
    "BG": 16.0,
    "CH": 42.0,
    "CZ": 20.0,
    "DE": 30.0,
    "DK": 38.0,
    "EE": 22.0,
    "ES": 26.0,
    "FI": 34.0,
    "FR": 32.0,
    "GB": 34.0,
    "GR": 24.0,
    "HR": 22.0,
    "HU": 18.0,
    "IE": 32.0,
    "IT": 28.0,
    "LT": 20.0,
    "LU": 36.0,
    "LV": 20.0,
    "NL": 32.0,
    "NO": 44.0,
    "PL": 16.0,
    "PT": 22.0,
    "RO": 16.0,
    "RS": 16.0,
    "SE": 34.0,
    "SI": 22.0,
    "SK": 18.0,
    "TR": 15.0,
    "UA": 14.0,
}

# Città dove il livello nazionale non basta (capitali e mete care).
FOOD_BY_CITY: dict[str, float] = {
    "zurigo": 46.0,
    "ginevra": 46.0,
    "oslo": 46.0,
    "copenaghen": 40.0,
    "londra": 38.0,
    "parigi": 36.0,
    "amsterdam": 34.0,
    "bruxelles": 33.0,
    "stoccolma": 36.0,
    "helsinki": 35.0,
    "dublino": 34.0,
    "monaco": 33.0,
    "amburgo": 32.0,
    "lubiana": 24.0,
    "lubiana (ljubljana)": 24.0,
}

# Paese (ISO-2) -> biglietti/attrazioni a persona al giorno, in EUR.
ACTIVITIES_BY_COUNTRY: dict[str, float] = {
    "AT": 10.0, "BE": 11.0, "BG": 6.0, "CH": 14.0, "CZ": 8.0, "DE": 10.0,
    "DK": 13.0, "EE": 8.0, "ES": 10.0, "FI": 12.0, "FR": 12.0, "GB": 13.0,
    "GR": 8.0, "HR": 8.0, "HU": 7.0, "IE": 11.0, "IT": 11.0, "LT": 7.0,
    "LU": 12.0, "LV": 7.0, "NL": 12.0, "NO": 15.0, "PL": 6.0, "PT": 8.0,
    "RO": 6.0, "RS": 6.0, "SE": 12.0, "SI": 8.0, "SK": 7.0, "TR": 10.0,
    "UA": 5.0,
}

DEFAULT_FOOD = 26.0
DEFAULT_ACTIVITIES = 9.0


@dataclass(slots=True)
class Estimate:
    """Stima di spesa quotidiana per un soggiorno."""

    food_per_day: float
    activities_per_day: float
    days: int
    adults: int
    food_total: float
    activities_total: float
    currency: str = "EUR"
    basis: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def total(self) -> float:
        return self.food_total + self.activities_total


def daily_rates(city: str, country: str = "") -> tuple[float, float, str]:
    """(cibo, attrazioni) a persona al giorno, con la base della stima."""
    city_key = (city or "").strip().casefold()
    country_key = (country or "").strip().upper()
    if city_key in FOOD_BY_CITY:
        food = FOOD_BY_CITY[city_key]
        basis = f"livello città ({city})"
    elif country_key in FOOD_BY_COUNTRY:
        food = FOOD_BY_COUNTRY[country_key]
        basis = f"livello paese ({country_key})"
    else:
        food = DEFAULT_FOOD
        basis = "stima generica (paese non in tabella)"
    activities = ACTIVITIES_BY_COUNTRY.get(country_key, DEFAULT_ACTIVITIES)
    return food, activities, basis


def estimate_stay(
    *,
    city: str,
    country: str = "",
    nights: int,
    adults: int = 1,
    currency: str = "EUR",
    food_per_day: float | None = None,
    activities_per_day: float | None = None,
) -> Estimate:
    """Stima per `nights` notti: i giorni sul posto sono nights + 1."""
    food_rate, activity_rate, basis = daily_rates(city, country)
    if food_per_day is not None:
        food_rate, basis = float(food_per_day), "valore fornito dall'utente"
    if activities_per_day is not None:
        activity_rate = float(activities_per_day)
    days = max(1, int(nights) + 1)
    return Estimate(
        food_per_day=food_rate,
        activities_per_day=activity_rate,
        days=days,
        adults=max(1, int(adults)),
        food_total=round(food_rate * days * max(1, int(adults)), 2),
        activities_total=round(activity_rate * days * max(1, int(adults)), 2),
        currency=currency,
        basis=basis,
    )


ESTIMATE_DISCLAIMER = (
    "Stime indicative, non preventivi: cibo e attrazioni sono calcolati su una spesa "
    "quotidiana da viaggio economico (bar/supermercato e un biglietto al giorno) per "
    "persona, sui giorni di presenza (notti + 1)."
)
