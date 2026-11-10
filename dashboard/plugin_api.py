"""Backend del pannello Desktop di tripscout.

Espone le ricerche come job: una ricerca vera dura decine di secondi, quindi
`POST /search` risponde subito con un id e il pannello interroga `/jobs/<id>`.
Nessuna scorciatoia: qui gira lo stesso motore dei tool dell'agente.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from tripscout_core import cities, origins, store, tools  # noqa: E402

router = APIRouter()

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_MAX_JOBS = 12


def _prune() -> None:
    with _LOCK:
        if len(_JOBS) <= _MAX_JOBS:
            return
        for key in sorted(_JOBS, key=lambda k: _JOBS[k]["started"])[: len(_JOBS) - _MAX_JOBS]:
            _JOBS.pop(key, None)


def _run_job(job_id: str, params: dict[str, Any]) -> None:
    job = _JOBS[job_id]
    try:
        raw = tools.search(params)
        import json

        payload = json.loads(raw)
        if "error" in payload and "options" not in payload:
            job["status"] = "error"
            job["error"] = payload["error"]
        else:
            job["status"] = "done"
            job["result"] = payload
    except Exception as exc:  # noqa: BLE001 — il pannello deve mostrare l'errore, non sparire
        job["status"] = "error"
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["finished"] = time.time()


@router.get("/presets")
async def presets() -> dict[str, Any]:
    """Tutto ciò che il pannello deve mostrare nei menu, senza rete."""
    homes = []
    for name in origins.known_cities():
        preset = origins.resolve(name)
        if preset is None:
            continue
        homes.append(
            {
                "city": preset.city,
                "region": preset.region,
                "airports": [
                    {"airport": a.airport, "airport_city": a.airport_city,
                     "access_cost": a.access_cost, "how": a.how}
                    for a in preset.airports
                ],
            }
        )
    return {
        "home_cities": homes,
        "destinations": [
            {
                "city": c.city,
                "country": c.country,
                "airports": c.airports,
                "transfer_cost": c.transfer_cost,
                "region": c.region,
            }
            for c in cities.all_cities()
        ],
        "regions": cities.regions(),
        "lodging": ["any", "hostel", "hotel", "apartment"],
        "currencies": ["EUR", "USD", "GBP", "CHF", "PLN", "HUF", "CZK"],
        "defaults": {
            "nights_min": 2,
            "nights_max": 4,
            "weekdays": ["thursday", "friday"],
            "adults": 1,
            "rooms": 1,
            "estimates": True,
            "max_requests": 60,
            "min_interval": 0.8,
        },
        "cache": store.cache_stats(),
    }


@router.post("/search")
async def start_search(body: dict[str, Any]) -> dict[str, Any]:
    """Avvia una ricerca e restituisce subito l'id del job."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")

    params = dict(body)
    # il pannello manda i nomi delle città: qui diventano aeroporti e transfer
    raw_destinations = params.get("destinations")
    picked = (
        [str(x) for x in raw_destinations]
        if isinstance(raw_destinations, list)
        else ([str(raw_destinations)] if raw_destinations else [])
    )
    wants_any = not picked or any(name.strip().casefold() in ("any", "no matter", "*") for name in picked)
    if wants_any:
        limit = params.get("max_destinations") or 8
        try:
            limit = max(1, min(12, int(limit)))
        except (TypeError, ValueError):
            limit = 8
        params["destinations"] = [c.as_destination() for c in cities.shortlist(limit)]
        params["destinations_mode"] = "any"
    else:
        resolved = cities.as_destinations(picked)
        if resolved:
            params["destinations"] = resolved
        else:
            raise HTTPException(
                status_code=400,
                detail="none of those cities is known: pick from the list or write 'any'",
            )

    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "started": time.time(),
            "finished": None,
            "error": None,
            "result": None,
            "params": params,
        }
    _prune()
    threading.Thread(target=_run_job, args=(job_id, params), daemon=True).start()
    return {"job_id": job_id, "params": params}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    elapsed = (job.get("finished") or time.time()) - job["started"]
    payload: dict[str, Any] = {
        "status": job["status"],
        "elapsed_seconds": round(elapsed, 1),
    }
    if job["error"]:
        payload["error"] = job["error"]
    if job["result"] is not None:
        payload["result"] = job["result"]
    return payload


@router.get("/cache")
async def cache() -> dict[str, Any]:
    return store.cache_stats()


@router.post("/cache/clear")
async def cache_clear() -> dict[str, Any]:
    removed = store.clear()
    return {"removed": removed, **store.cache_stats()}
