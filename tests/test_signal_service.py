from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.regime import (
    RegimeConditions,
    RegimeIndicators,
    RegimeResponse,
    SignalRead,
)
from app.services.signal_service import SignalService


def _make_response(timestamp: datetime, action: str = "BUY") -> RegimeResponse:
    return RegimeResponse(
        symbol="BTC/USDT",
        timeframe="4h",
        action=action,
        regime_on=action != "CASH",
        previous_regime_on=False,
        confidence=80,
        price=50000.0,
        timestamp=timestamp,
        decision_timestamp=timestamp - timedelta(hours=4),
        indicators=RegimeIndicators(close=50000, ema_50=49000, ema_200=48000, rsi_14=55),
        conditions=RegimeConditions(
            close_above_ema50=True,
            close_above_ema200=True,
            ema50_above_ema200=True,
            ema50_rising=True,
            ema200_rising=True,
            rsi_above_50=True,
        ),
        reasoning="test",
        warning="test",
    )


class InMemorySignalStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert_if_absent(self, payload: dict[str, Any]) -> SignalRead | None:
        if any(
            row["pair"] == payload["pair"]
            and row["signal_timestamp"] == payload["signal_timestamp"]
            for row in self.rows
        ):
            return None

        row = {
            **payload,
            "id": len(self.rows) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.rows.append(row)
        return SignalRead.model_validate(row)

    async def get_by_candle(
        self, pair: str, signal_timestamp: datetime
    ) -> SignalRead | None:
        timestamp = signal_timestamp.isoformat()
        for row in self.rows:
            if row["pair"] == pair and row["signal_timestamp"] == timestamp:
                return SignalRead.model_validate(row)
        return None

    async def list_signals(
        self, pair: str | None, limit: int
    ) -> list[SignalRead]:
        rows = [row for row in self.rows if pair is None or row["pair"] == pair]
        rows.sort(key=lambda row: row["signal_timestamp"], reverse=True)
        return [SignalRead.model_validate(row) for row in rows[:limit]]


async def test_persist_creates_signal() -> None:
    store = InMemorySignalStore()
    service = SignalService(store=store)
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    stored = await service.persist(_make_response(ts))

    assert stored is not None
    assert stored.id == 1
    assert stored.pair == "BTC/USDT"
    assert stored.action == "BUY"
    assert stored.conditions["rsi_above_50"] is True


async def test_persist_dedupes_same_candle() -> None:
    store = InMemorySignalStore()
    service = SignalService(store=store)
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    first = await service.persist(_make_response(ts))
    second = await service.persist(_make_response(ts, action="HOLD"))

    assert first is not None
    assert second is None
    assert len(store.rows) == 1


async def test_list_signals_filters_and_orders_by_timestamp() -> None:
    store = InMemorySignalStore()
    service = SignalService(store=store)
    ts = datetime(2026, 6, 11, 16, 0, tzinfo=timezone.utc)

    await service.persist(_make_response(ts))
    await service.persist(_make_response(ts + timedelta(hours=1)))

    signals = await service.list_signals("BTC/USDT", limit=1)

    assert len(signals) == 1
    assert signals[0].signal_timestamp == ts + timedelta(hours=1)
