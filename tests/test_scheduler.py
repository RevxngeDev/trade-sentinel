from __future__ import annotations

import inspect
from types import SimpleNamespace

from apscheduler.triggers.cron import CronTrigger

from app.config import Settings, settings
from app.core import scheduler as scheduler_module


def test_scheduler_cron_is_valid() -> None:
    trigger = CronTrigger.from_crontab(settings.scheduler_cron, timezone="UTC")
    assert trigger is not None


def test_capture_job_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(scheduler_module.capture_signal_job)


def test_scheduler_disabled_by_default() -> None:
    # Evita llamadas de red en dev/tests salvo que se active explícitamente.
    assert Settings(_env_file=None).scheduler_enabled is False


async def test_capture_job_evaluates_pending_signals_before_capture(monkeypatch) -> None:
    events: list[str] = []

    class FakeTrackerService:
        async def evaluate_pending(self):
            events.append("tracking")
            return SimpleNamespace(scanned=0, eligible=0, created=0, skipped_existing=0)

    class FakeSignalService:
        async def generate_and_store(self, symbol: str):
            events.append(f"capture:{symbol}")
            return None, None

    monkeypatch.setattr(scheduler_module, "TrackerService", FakeTrackerService)
    monkeypatch.setattr(scheduler_module, "SignalService", FakeSignalService)

    await scheduler_module.capture_signal_job()

    assert events == ["tracking", f"capture:{settings.default_symbol}"]


async def test_ai_opinion_is_recorded_after_the_signal_is_stored(monkeypatch) -> None:
    """
    La opinión se pide DESPUÉS de decidir y guardar. Si se pidiera antes, la IA
    estaría en la ruta de decisión.
    """
    events: list[str] = []
    stored_signal = SimpleNamespace(
        action="CASH", pair="BTC/USDT", signal_timestamp="2026-08-26T08:00:00Z"
    )

    class FakeTrackerService:
        async def evaluate_pending(self):
            return SimpleNamespace(scanned=0, eligible=0, created=0, skipped_existing=0)

    class FakeSignalService:
        async def generate_and_store(self, symbol: str):
            events.append("stored")
            return None, stored_signal

    class FakeAIOpinionService:
        async def record_for_signal(self, signal):
            events.append("opinion")
            return None

    async def fake_alert(signal):
        events.append("alert")

    monkeypatch.setattr(scheduler_module, "TrackerService", FakeTrackerService)
    monkeypatch.setattr(scheduler_module, "SignalService", FakeSignalService)
    monkeypatch.setattr(scheduler_module, "AIOpinionService", FakeAIOpinionService)
    monkeypatch.setattr(scheduler_module, "send_signal_alert", fake_alert)

    await scheduler_module.capture_signal_job()

    assert events == ["stored", "opinion", "alert"]


async def test_capture_survives_a_failing_ai_opinion(monkeypatch) -> None:
    """Un fallo del registro de IA no puede impedir la alerta de la señal."""
    events: list[str] = []

    class FakeTrackerService:
        async def evaluate_pending(self):
            return SimpleNamespace(scanned=0, eligible=0, created=0, skipped_existing=0)

    class FakeSignalService:
        async def generate_and_store(self, symbol: str):
            return None, SimpleNamespace(
                action="CASH", pair="BTC/USDT", signal_timestamp="2026-08-26T08:00:00Z"
            )

    class ExplodingAIOpinionService:
        async def record_for_signal(self, signal):
            raise RuntimeError("groq caído")

    async def fake_alert(signal):
        events.append("alert")

    monkeypatch.setattr(scheduler_module, "TrackerService", FakeTrackerService)
    monkeypatch.setattr(scheduler_module, "SignalService", FakeSignalService)
    monkeypatch.setattr(scheduler_module, "AIOpinionService", ExplodingAIOpinionService)
    monkeypatch.setattr(scheduler_module, "send_signal_alert", fake_alert)

    await scheduler_module.capture_signal_job()

    assert events == ["alert"], "la alerta debe enviarse aunque la IA falle"
