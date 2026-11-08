"""tripscout — il viaggio più economico, con volo e hotel confrontati insieme.

Il plugin registra tre tool e nient'altro: nessun override di tool di Hermes,
nessuna patch, solo `ctx.register_tool`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# La directory del plugin entra nel path, così il package `tripscout_core` è
# importabile per nome. I moduli NON restano di primo livello: nomi generici
# come `tools` o `schemas` collidono con i moduli core già in sys.modules.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from tripscout_core import schemas, tools  # noqa: E402

TOOLSET = "tripscout"

__all__ = ["register", "TOOLSET"]


def register(ctx) -> None:
    """Registra i tre tool del plugin nel toolset `tripscout`."""
    for schema, handler in (
        (schemas.SEARCH, tools.search),
        (schemas.PRICE_TRIP, tools.price_trip),
        (schemas.HISTORY, tools.history),
    ):
        ctx.register_tool(
            name=schema["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
        )
