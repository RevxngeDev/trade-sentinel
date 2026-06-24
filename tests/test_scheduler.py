from __future__ import annotations

import inspect
from types import SimpleNamespace

from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.core import scheduler as scheduler_module


def test_scheduler_cron_is_valid() -> None:
    trigger = CronTrigger.from_crontab(settings.scheduler_cron, timezone="UTC")
    assert trigger is not None


def test_capture_job_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(scheduler_module.capture_signal_job)


def test_scheduler_disabled_by_default() -> None:
    # Evita llamadas de red en dev/tests salvo que se active explícitamente.
    assert settings.scheduler_enabled is False


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
