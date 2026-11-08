"""Generazione delle finestre di viaggio (partenza, ritorno, notti)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAY_NAMES = {
    "mon": 0, "monday": 0, "lun": 0, "lunedi": 0, "lunedì": 0,
    "tue": 1, "tuesday": 1, "mar": 1, "martedi": 1, "martedì": 1,
    "wed": 2, "wednesday": 2, "mer": 2, "mercoledi": 2, "mercoledì": 2,
    "thu": 3, "thursday": 3, "gio": 3, "giovedi": 3, "giovedì": 3,
    "fri": 4, "friday": 4, "ven": 4, "venerdi": 4, "venerdì": 4,
    "sat": 5, "saturday": 5, "sab": 5, "sabato": 5,
    "sun": 6, "sunday": 6, "dom": 6, "domenica": 6,
}


@dataclass(frozen=True, slots=True)
class Trip:
    depart: date
    ret: date
    nights: int

    @property
    def label(self) -> str:
        return f"{self.depart.isoformat()} → {self.ret.isoformat()} ({self.nights}n)"


def parse_weekdays(values) -> set[int]:
    """Nomi di giorno (en/it, abbreviati o interi) -> numeri 0=lunedì."""
    if not values:
        return set()
    if isinstance(values, (str, int)):
        values = [values]
    out: set[int] = set()
    for value in values:
        if isinstance(value, int) and 0 <= value <= 6:
            out.add(value)
            continue
        key = str(value).strip().casefold()
        if key.isdigit() and 0 <= int(key) <= 6:
            out.add(int(key))
        elif key in WEEKDAY_NAMES:
            out.add(WEEKDAY_NAMES[key])
    return out


def trips(
    window_start: date,
    window_end: date,
    nights_min: int = 2,
    nights_max: int = 4,
    weekdays: set[int] | None = None,
    max_options: int = 40,
) -> list[Trip]:
    """Tutte le combinazioni partenza/ritorno nella finestra, per data crescente.

    `weekdays` filtra il giorno di partenza: per un weekend lungo italiano
    3=giovedì e 4=venerdì sono i giorni utili.
    """
    if window_end < window_start:
        raise ValueError("window_end precede window_start")
    nights_min = max(1, int(nights_min))
    nights_max = max(nights_min, int(nights_max))
    found: list[Trip] = []
    day = window_start
    while day <= window_end:
        if not weekdays or day.weekday() in weekdays:
            for nights in range(nights_min, nights_max + 1):
                ret = day + timedelta(days=nights)
                if ret <= window_end:
                    found.append(Trip(depart=day, ret=ret, nights=nights))
        day += timedelta(days=1)
    found.sort(key=lambda t: (t.depart, t.nights))
    return found[: max(1, int(max_options))]


def weekend_windows(count: int = 2, *, today: date | None = None,
                    min_lead_days: int = 10) -> list[tuple[date, date]]:
    """Le prossime `count` finestre da giovedì a domenica (default del tool)."""
    import datetime as _dt

    now = today or _dt.date.today()
    start = now + timedelta(days=max(0, min_lead_days))
    # primo giovedì utile
    start += timedelta(days=(3 - start.weekday()) % 7)
    out: list[tuple[date, date]] = []
    for i in range(max(1, count)):
        thu = start + timedelta(days=7 * i)
        out.append((thu, thu + timedelta(days=3)))
    return out
