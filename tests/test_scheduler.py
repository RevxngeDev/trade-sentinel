from __future__ import annotations

import inspect

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
