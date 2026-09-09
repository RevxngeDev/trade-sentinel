from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.jobs.heartbeat as heartbeat
from app.config import Settings, settings


NOW = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, timestamps: list[datetime]) -> None:
        self.timestamps = timestamps

    async def list_signals(self, pair: str, limit: int):
        return [SimpleNamespace(signal_timestamp=ts) for ts in self.timestamps]


def _complete_boundaries(*, now: datetime = NOW, days: int = 9) -> list[datetime]:
    """Todas las fronteras 4h de los últimos `days` días: un registro sano."""
    start = now - timedelta(days=days)
    start = start.replace(minute=0, second=0, microsecond=0)
    start -= timedelta(hours=start.hour % 4)

    slots: list[datetime] = []
    current = start
    while current <= now:
        slots.append(current)
        current += timedelta(hours=4)
    return slots


async def _run(timestamps: list[datetime], now: datetime = NOW):
    alerts: list[str] = []

    async def alert(text: str) -> None:
        alerts.append(text)

    status = await heartbeat.check(store=FakeStore(timestamps), alert=alert, now=now)
    return status, alerts


# ============================================================
# Umbral de "detenida"
# ============================================================


def test_stale_threshold_is_calibrated_to_actions_delays() -> None:
    """
    8h producía falsas alarmas: los crons de Actions se retrasan 9-14h y el
    backfill lo cura solo. Ver DECISIONS 2026-08-26.
    """
    assert Settings(_env_file=None).heartbeat_max_age_hours == 14


async def test_ok_when_recent_and_complete() -> None:
    status, alerts = await _run(_complete_boundaries())
    assert status == "ok"
    assert alerts == []


async def test_a_nine_hour_delay_no_longer_alerts() -> None:
    """Regresión de las 2 falsas alarmas reales del 27 y 28 de agosto."""
    boundaries = [ts for ts in _complete_boundaries() if ts <= NOW - timedelta(hours=9)]

    status, alerts = await _run(boundaries)

    assert status == "ok"
    assert alerts == []


async def test_alerts_when_truly_stale() -> None:
    boundaries = [ts for ts in _complete_boundaries() if ts <= NOW - timedelta(hours=20)]

    status, alerts = await _run(boundaries)

    assert status == "stale"
    assert "DETENIDA" in alerts[0]


async def test_alerts_when_empty() -> None:
    status, alerts = await _run([])
    assert status == "empty"
    assert len(alerts) == 1


# ============================================================
# Huecos en el registro
# ============================================================


async def test_alerts_on_a_hole_the_backfill_left() -> None:
    boundaries = _complete_boundaries()
    hole = NOW - timedelta(days=3)
    hole = hole.replace(minute=0, second=0, microsecond=0)
    hole -= timedelta(hours=hole.hour % 4)
    boundaries.remove(hole)

    status, alerts = await _run(boundaries)

    assert status == "gaps"
    assert "HUECOS" in alerts[0]
    assert f"{hole:%m-%d %H:%M}" in alerts[0]


async def test_recent_missing_boundary_is_not_a_hole() -> None:
    """
    Una frontera recién cerrada puede estar esperando a la próxima corrida.
    Reclamarla sería reintroducir la falsa alarma por otra vía.
    """
    boundaries = _complete_boundaries()
    del boundaries[-1]

    status, alerts = await _run(boundaries)

    assert status == "ok"
    assert alerts == []


async def test_stale_is_reported_before_gaps() -> None:
    """Si no entra nada, el hueco tampoco se va a rellenar: manda la causa."""
    boundaries = [ts for ts in _complete_boundaries() if ts <= NOW - timedelta(hours=20)]
    del boundaries[10]

    status, alerts = await _run(boundaries)

    assert status == "stale"
    assert len(alerts) == 1


# ============================================================
# Helpers puros
# ============================================================


def test_expected_slots_are_four_hour_boundaries() -> None:
    slots = heartbeat.expected_four_hour_slots(
        since=NOW - timedelta(days=1),
        until=NOW,
    )

    assert len(slots) == 6
    assert all(slot.hour % 4 == 0 and slot.minute == 0 for slot in slots)
    assert all(NOW - timedelta(days=1) <= slot <= NOW for slot in slots)


def test_find_missing_slots_respects_the_grace_window() -> None:
    stored: set[datetime] = set()

    missing = heartbeat.find_missing_slots(
        stored,
        now=NOW,
        lookback_days=1,
        grace_hours=14,
    )

    # Con todo vacío solo se reclama lo anterior a la ventana de gracia.
    assert missing
    assert max(missing) <= NOW - timedelta(hours=14)


def test_find_missing_slots_returns_nothing_when_complete() -> None:
    stored = set(_complete_boundaries())

    missing = heartbeat.find_missing_slots(
        stored,
        now=NOW,
        lookback_days=settings.backfill_lookback_days,
        grace_hours=settings.heartbeat_max_age_hours,
    )

    assert missing == []


# ============================================================
# Vigilancia del registro de IA
#
# Contexto: el 2026-09-09 se descubrió que Groq había retirado el modelo y el
# registro llevaba ~2 semanas guardando solo errores sin que nadie avisara.
# ============================================================


class FakeOpinionStore:
    def __init__(self, statuses: list[str], reason: str = "404 model not found") -> None:
        self.statuses = statuses
        self.reason = reason

    async def list_opinions(self, limit: int):
        return [
            SimpleNamespace(
                status=status,
                error_reason=self.reason if status != "ok" else None,
            )
            for status in self.statuses[:limit]
        ]


async def _run_ai(statuses: list[str]):
    alerts: list[str] = []

    async def alert(text: str) -> None:
        alerts.append(text)

    broken = await heartbeat.ai_logging_is_broken(
        FakeOpinionStore(statuses), alert=alert
    )
    return broken, alerts


async def test_sustained_ai_failure_alerts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)

    broken, alerts = await _run_ai(["error"] * settings.heartbeat_ai_sample_size)

    assert broken is True
    assert len(alerts) == 1
    assert "404 model not found" in alerts[0]
    # Debe dejar claro que la captura sigue sana, para no provocar un susto.
    assert "NO está afectada" in alerts[0]


async def test_one_recovered_opinion_is_not_an_outage(monkeypatch) -> None:
    """Un timeout suelto se recupera solo: avisar de eso es fatiga de alertas."""
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)

    statuses = ["ok"] + ["error"] * (settings.heartbeat_ai_sample_size - 1)
    broken, alerts = await _run_ai(statuses)

    assert broken is False
    assert alerts == []


async def test_too_few_opinions_does_not_alert(monkeypatch) -> None:
    """Recién activado no hay muestra para distinguir avería de arranque."""
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)

    broken, alerts = await _run_ai(["error", "error"])

    assert broken is False
    assert alerts == []


async def test_disabled_logging_is_not_watched(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", False)

    broken, alerts = await _run_ai(["error"] * 20)

    assert broken is False
    assert alerts == []


async def test_capture_problems_are_reported_before_ai_problems(monkeypatch) -> None:
    """
    Una captura detenida es más grave: si no entran señales, tampoco hay
    opiniones que registrar. El aviso de IA no debe tapar el de captura.
    """
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)
    alerts: list[str] = []

    async def alert(text: str) -> None:
        alerts.append(text)

    stale = [NOW - timedelta(hours=40)]
    status = await heartbeat.check(
        store=FakeStore(stale),
        alert=alert,
        now=NOW,
        opinion_store=FakeOpinionStore(["error"] * 20),
    )

    assert status == "stale"
    assert len(alerts) == 1
    assert "DETENIDA" in alerts[0]


async def test_healthy_capture_still_surfaces_broken_ai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_opinion_logging_enabled", True)
    alerts: list[str] = []

    async def alert(text: str) -> None:
        alerts.append(text)

    status = await heartbeat.check(
        store=FakeStore(_complete_boundaries()),
        alert=alert,
        now=NOW,
        opinion_store=FakeOpinionStore(["error"] * 20),
    )

    assert status == "ai_failing"
    assert len(alerts) == 1
