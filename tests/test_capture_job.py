from __future__ import annotations

from types import SimpleNamespace

import app.jobs.capture as capture_module
from app.config import settings


async def test_run_backfills_before_capturing(monkeypatch) -> None:
    events: list[str] = []

    class FakeSignalService:
        async def backfill(self, symbol: str):
            events.append(f"backfill:{symbol}")
            return SimpleNamespace(
                scanned=0, created=0, skipped_existing=0, skipped_insufficient=0
            )

    async def fake_capture() -> None:
        events.append("capture")

    monkeypatch.setattr(capture_module, "SignalService", FakeSignalService)
    monkeypatch.setattr(capture_module, "capture_signal_job", fake_capture)

    await capture_module.run()

    # Primero rellena huecos, luego captura/evalúa/alerta la vela actual.
    assert events == [f"backfill:{settings.default_symbol}", "capture"]
