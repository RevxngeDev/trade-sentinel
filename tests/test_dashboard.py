from __future__ import annotations

from datetime import datetime, timezone

from app.api.routes.dashboard import dashboard
from app.api.routes import stats as stats_routes
from app.schemas.regime import SignalResultRead


async def test_dashboard_serves_read_only_personal_page() -> None:
    html = await dashboard()

    assert "TradeSentinel" in html
    assert "no ejecuta operaciones" in html
    assert 'fetch("/stats")' in html
    assert 'fetch("/signals?pair=BTC%2FUSDT&limit=500")' in html
    assert 'fetch("/tracking/results?limit=500")' in html
    # Gráficos de distribución (sin dependencias externas).
    assert 'id="actionChart"' in html
    assert 'id="outcomeChart"' in html


async def test_tracking_results_route_lists_recent_results(monkeypatch) -> None:
    calls: list[int] = []

    class FakeTrackerService:
        async def list_results(self, limit: int):
            calls.append(limit)
            return [
                SignalResultRead(
                    id=1,
                    signal_id=2,
                    outcome="cash",
                    pnl_pct=0.0,
                    evaluated_at=datetime(2026, 6, 27, tzinfo=timezone.utc),
                )
            ]

    monkeypatch.setattr(stats_routes, "TrackerService", FakeTrackerService)

    results = await stats_routes.list_tracking_results(limit=7)

    assert calls == [7]
    assert results[0].signal_id == 2
    assert results[0].outcome == "cash"
