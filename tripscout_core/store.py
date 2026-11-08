"""Cache e storico prezzi, in SQLite sotto `<hermes home>/plugin-data/tripscout/`.

La cache è ciò che rende praticabile la ricerca congiunta: la prima passata
costa un certo numero di richieste, le successive sono quasi gratuite.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

PLUGIN_NAME = "tripscout"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    kind     TEXT NOT NULL,
    key      TEXT NOT NULL,
    price    REAL,
    currency TEXT,
    seen_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS history_lookup ON history (kind, key, seen_at);
"""

_conn: sqlite3.Connection | None = None


def connect() -> sqlite3.Connection:
    """Connessione condivisa; usa plugin_db() di Hermes, con fallback autonomo."""
    global _conn
    if _conn is not None:
        return _conn
    try:
        from plugins.plugin_storage import plugin_db  # type: ignore[import-not-found]

        conn = plugin_db(PLUGIN_NAME)
    except Exception:
        import os
        from pathlib import Path

        path = Path(
            os.environ.get("TRIPSCOUT_DB") or (Path.home() / ".tripscout" / "data.db")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
    conn.executescript(_SCHEMA)
    conn.commit()
    _conn = conn
    return conn


def _key(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def get(kind: str, key: str, ttl_hours: float) -> Any | None:
    """Payload in cache se più giovane di `ttl_hours`, altrimenti None."""
    row = connect().execute(
        "SELECT payload, fetched_at FROM cache WHERE key = ?", (_key(kind, key),)
    ).fetchone()
    if not row:
        return None
    if ttl_hours >= 0 and time.time() - float(row[1]) > ttl_hours * 3600:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def put(kind: str, key: str, payload: Any) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO cache (key, kind, payload, fetched_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, fetched_at = excluded.fetched_at",
        (_key(kind, key), kind, json.dumps(payload), time.time()),
    )
    conn.commit()


def record_price(kind: str, key: str, price: float | None, currency: str) -> None:
    """Aggiunge un'osservazione di prezzo allo storico (solo se c'è un prezzo)."""
    if price is None:
        return
    conn = connect()
    conn.execute(
        "INSERT INTO history (kind, key, price, currency, seen_at) VALUES (?, ?, ?, ?, ?)",
        (kind, key, float(price), currency, time.time()),
    )
    conn.commit()


def price_history(kind: str, key: str, limit: int = 30) -> list[dict[str, Any]]:
    """Osservazioni più recenti prima, con il minimo osservato."""
    rows = connect().execute(
        "SELECT price, currency, seen_at FROM history WHERE kind = ? AND key = ? "
        "ORDER BY seen_at DESC LIMIT ?",
        (kind, key, max(1, int(limit))),
    ).fetchall()
    out = [
        {"price": float(r[0]), "currency": r[1], "seen_at": float(r[2])}
        for r in rows
        if r[0] is not None
    ]
    if out:
        lowest = min(out, key=lambda r: r["price"])
        out.append(
            {
                "summary": "lowest_observed",
                "price": lowest["price"],
                "currency": lowest["currency"],
                "seen_at": lowest["seen_at"],
            }
        )
    return out


def cache_stats() -> dict[str, int]:
    conn = connect()
    cache_rows = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
    history_rows = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    return {"cached_entries": int(cache_rows), "price_observations": int(history_rows)}


def clear(kind: str | None = None) -> int:
    conn = connect()
    if kind:
        cur = conn.execute("DELETE FROM cache WHERE kind = ?", (kind,))
    else:
        cur = conn.execute("DELETE FROM cache")
    conn.commit()
    return cur.rowcount
