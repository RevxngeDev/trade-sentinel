from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.schemas.regime import SignalRead, SignalResultRead
from app.services.tracker_service import TrackerService


def _signal(action: str = "BUY") -> SignalRead:
    timestamp = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    return SignalRead(
        id=1,
        pair="BTC/USDT",
        timeframe="4h",
        action=action,
        regime_on=action != "CASH",
        previous_regime_on=False,
        confidence=80,
        price=100.0,
        signal_timestamp=timestamp,
        decision_timestamp=timestamp - timedelta(hours=4),
        conditions={},
        indicators={},
        reasoning="test",
        created_at=timestamp,
    )


class FakeSignalStore:
    def __init__(self, signals: list[SignalRead]) -> None:
        self.signals = signals

    async def list_signals(self, pair: str | None, limit: int) -> list[SignalRead]:
        return [
            signal
            for signal in self.signals
            if pair is None or signal.pair == pair
        ][:limit]


class FakeResultStore:
    def __init__(self) -> None:
        self.results: list[SignalResultRead] = []

    async def list_result_signal_ids(self, limit: int) -> set[int]:
        return {result.signal_id for result in self.results[:limit]}

    async def insert_if_absent(
        self, signal_id: int, outcome: str, pnl_pct: float
    ) -> SignalResultRead | None:
        if any(result.signal_id == signal_id for result in self.results):
            return None
        result = SignalResultRead(
            id=len(self.results) + 1,
            signal_id=signal_id,
            outcome=outcome,
            pnl_pct=pnl_pct,
            evaluated_at=datetime.now(timezone.utc),
        )
        self.results.append(result)
        return result

    async def list_results(self, limit: int) -> list[SignalResultRead]:
        return self.results[:limit]


class FakeMarketData:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = 0

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        self.calls += 1
        assert symbol == "BTC/USDT"
        assert timeframe == "1h"
        return self.frame


def _frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-06-22T13:00:00Z",
            "2026-06-22T14:00:00Z",
        ]
    )
    return pd.DataFrame({"close": [105.0, 110.0]}, index=index)


async def test_tracker_waits_until_forward_candle_is_closed() -> None:
    signal_store = FakeSignalStore([_signal()])
    result_store = FakeResultStore()
    market_data = FakeMarketData(_frame())
    tracker = TrackerService(
        signal_store=signal_store,
        result_store=result_store,
        market_data=market_data,
        now_provider=lambda: datetime(2026, 6, 22, 14, 30, tzinfo=timezone.utc),
    )

    run = await tracker.evaluate_pending()

    assert run.created == 0
    assert not result_store.results
    assert market_data.calls == 0


async def test_tracker_records_forward_buy_return_after_closed_horizon() -> None:
    signal_store = FakeSignalStore([_signal()])
    result_store = FakeResultStore()
    tracker = TrackerService(
        signal_store=signal_store,
        result_store=result_store,
        market_data=FakeMarketData(_frame()),
        now_provider=lambda: datetime(2026, 6, 22, 15, 1, tzinfo=timezone.utc),
    )

    run = await tracker.evaluate_pending()

    assert run.created == 1
    assert result_store.results[0].outcome == "gain"
    assert result_store.results[0].pnl_pct == 10.0


async def test_tracker_records_cash_as_zero_exposure() -> None:
    signal_store = FakeSignalStore([_signal("CASH")])
    result_store = FakeResultStore()
    tracker = TrackerService(
        signal_store=signal_store,
        result_store=result_store,
        market_data=FakeMarketData(_frame()),
        now_provider=lambda: datetime(2026, 6, 22, 15, 1, tzinfo=timezone.utc),
    )

    await tracker.evaluate_pending()
    stats = await tracker.get_stats()

    assert result_store.results[0].outcome == "cash"
    assert result_store.results[0].pnl_pct == 0.0
    assert stats.cash_signals == 1
    assert stats.average_active_return_pct is None
