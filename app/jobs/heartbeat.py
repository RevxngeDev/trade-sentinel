"""
Dead-man's switch: vigila que la captura de señales siga viva Y que el registro
no tenga agujeros.

Vigila DOS cosas distintas, porque son dos fallos distintos:

1. `stale` — hace demasiado que no entra una señal nueva. La captura puede estar
   caída. Umbral generoso (`heartbeat_max_age_hours`): el cron de GitHub Actions
   se retrasa a menudo y el backfill lo cura solo, así que avisar pronto era
   avisar de algo que se arreglaba sin intervención.

2. `gaps` — faltan fronteras de 4h YA CERRADAS que el backfill debería haber
   rellenado. Esto sí daña la muestra del paper trading y NO se cura solo.

Corre en un workflow SEPARADO del de captura (un vigilante independiente) y solo
lee Supabase, sin tocar el exchange. Si todo está sano, calla.

Uso: python -m app.jobs.heartbeat
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from app.bot.telegram_bot import send_text_alert
from app.config import settings
from app.services.signal_store import SupabaseSignalStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def expected_four_hour_slots(*, since: datetime, until: datetime) -> list[datetime]:
    """
    Fronteras 4h (00/04/08/12/16/20 UTC) entre `since` y `until`.

    Aritmética pura, sin pedir velas al exchange: el vigilante debe poder
    funcionar aunque el exchange esté caído o geobloqueado.
    """
    start = since.replace(minute=0, second=0, microsecond=0)
    start -= timedelta(hours=start.hour % 4)

    slots: list[datetime] = []
    current = start
    while current <= until:
        if current >= since:
            slots.append(current)
        current += timedelta(hours=4)
    return slots


def find_missing_slots(
    stored: set[datetime],
    *,
    now: datetime,
    lookback_days: int,
    grace_hours: int,
) -> list[datetime]:
    """
    Fronteras 4h que faltan y que ya deberían estar.

    `grace_hours` deja fuera la cola reciente: una frontera recién cerrada aún
    puede estar esperando a la próxima corrida, y eso no es un agujero. Solo se
    reclama lo que lleva sin rellenarse más tiempo del que tarda una corrida
    retrasada en llegar.
    """
    until = now - timedelta(hours=grace_hours)
    since = now - timedelta(days=lookback_days)

    return [
        slot
        for slot in expected_four_hour_slots(since=since, until=until)
        if slot not in stored
    ]


async def check(
    store: SupabaseSignalStore | None = None,
    alert: Callable[[str], Awaitable[None]] | None = None,
    now: datetime | None = None,
) -> str:
    """Devuelve 'ok' | 'stale' | 'gaps' | 'empty'. Alerta si no es 'ok'."""
    store = store or SupabaseSignalStore()
    alert = alert or send_text_alert
    now = now or datetime.now(timezone.utc)

    signals = await store.list_signals(
        settings.default_symbol, settings.tracking_scan_limit
    )

    if not signals:
        await alert("⚠️ TradeSentinel: no hay señales guardadas. Revisa la captura.")
        return "empty"

    latest = max(signal.signal_timestamp for signal in signals)
    age_hours = (now - latest).total_seconds() / 3600

    # La captura caída es más grave que un agujero: si no entra nada, el agujero
    # tampoco se va a rellenar. Se reporta primero.
    if age_hours > settings.heartbeat_max_age_hours:
        await alert(
            "⚠️ TradeSentinel: la captura parece DETENIDA. "
            f"Última señal hace {age_hours:.1f} h "
            f"({latest:%Y-%m-%d %H:%M} UTC). Revisa el workflow de GitHub Actions."
        )
        return "stale"

    missing = find_missing_slots(
        {signal.signal_timestamp for signal in signals},
        now=now,
        # El backfill solo repara dentro de su ventana: más atrás no tiene
        # sentido reclamarlo porque nadie lo va a rellenar.
        lookback_days=settings.backfill_lookback_days,
        grace_hours=settings.heartbeat_max_age_hours,
    )

    if missing:
        shown = ", ".join(f"{slot:%m-%d %H:%M}" for slot in missing[:5])
        extra = f" (+{len(missing) - 5} más)" if len(missing) > 5 else ""
        await alert(
            f"⚠️ TradeSentinel: el registro tiene {len(missing)} HUECOS que el "
            f"backfill no ha rellenado: {shown}{extra} UTC. "
            "La muestra del paper trading está incompleta."
        )
        return "gaps"

    logger.info(
        "Heartbeat OK: última señal hace %.1f h, sin huecos en %d días.",
        age_hours,
        settings.backfill_lookback_days,
    )
    return "ok"


def main() -> None:
    asyncio.run(check())


if __name__ == "__main__":
    main()
