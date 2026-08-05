from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.jobs.heartbeat as heartbeat


class FakeStore:
    def __init__(self, latest_ts: datetime | None) -> None:
        self.latest_ts = latest_ts

    async def list_signals(self, pair: str, limit: int):
        if self.latest_ts is None:
            return []
        return [SimpleNamespace(signal_timestamp=self.latest_ts)]


NOW = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)


async def _run(latest_ts):
    alerts: list[str] = []

    async def alert(text: str) -> None:
        alerts.append(text)

    status = await heartbeat.check(store=FakeStore(latest_ts), alert=alert, now=NOW)
    return status, alerts


async def test_ok_when_recent() -> None:
    status, alerts = await _run(NOW - timedelta(hours=3))
    assert status == "ok"
    assert alerts == []


async def test_alerts_when_stale() -> None:
    status, alerts = await _run(NOW - timedelta(hours=12))
    assert status == "stale"
    assert len(alerts) == 1


async def test_alerts_when_empty() -> None:
    status, alerts = await _run(None)
    assert status == "empty"
    assert len(alerts) == 1
