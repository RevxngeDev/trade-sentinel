"""Forward-only evaluation of persisted educational paper-trading signals."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

import pandas as pd

from app.config import settings
from app.schemas.regime import (
    SignalRead,
    SignalResultRead,
    SignalStatsRead,
    TrackingRunRead,
)
from app.services.market_data import MarketDataService
from app.services.signal_store import (
    SignalResultStore,
    SignalStore,
    SupabaseSignalResultStore,
    SupabaseSignalStore,
)


class TrackerService:
    """Evaluate saved signals only after their configured forward horizon closes."""

    def __init__(
        self,
        signal_store: SignalStore | None = None,
        result_store: SignalResultStore | None = None,
        market_data: MarketDataService | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.signal_store = signal_store or SupabaseSignalStore()
        self.result_store = result_store or SupabaseSignalResultStore()
        self.market_data = market_data or MarketDataService()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    async def evaluate_pending(self, limit: int | None = None) -> TrackingRunRead:
        scan_limit = limit or settings.tracking_scan_limit
        signals = await self.signal_store.list_signals(None, scan_limit)
        evaluated_ids = await self.result_store.list_result_signal_ids(scan_limit)
        now = self.now_provider()

        eligible = 0
        created = 0
        skipped_existing = 0
        frames: dict[str, pd.DataFrame] = {}

        for signal in signals:
            if signal.id in evaluated_ids:
                skipped_existing += 1
                continue

            exit_price = await self._forward_exit_price(signal, now, frames)
            if exit_price is None:
                continue

            eligible += 1
            outcome, pnl_pct = self._evaluate(signal, exit_price)
            result = await self.result_store.insert_if_absent(
                signal.id,
                outcome,
                pnl_pct,
            )
            if result is None:
                skipped_existing += 1
            else:
                created += 1

        return TrackingRunRead(
            scanned=len(signals),
            eligible=eligible,
            created=created,
            skipped_existing=skipped_existing,
        )

    async def get_stats(self) -> SignalStatsRead:
        signals = await self.signal_store.list_signals(None, settings.tracking_scan_limit)
        results = await self.result_store.list_results(settings.tracking_scan_limit)

        signal_by_id = {signal.id: signal for signal in signals}
        evaluated = [result for result in results if result.signal_id in signal_by_id]
        active = [result for result in evaluated if result.outcome != "cash"]
        cash_count = sum(1 for result in evaluated if result.outcome == "cash")
        gains = sum(1 for result in active if result.outcome == "gain")

        return SignalStatsRead(
            total_signals=len(signals),
            evaluated_signals=len(evaluated),
            pending_signals=max(0, len(signals) - len(evaluated)),
            active_signals=len(active),
            cash_signals=cash_count,
            active_win_rate_pct=(round((gains / len(active)) * 100, 2) if active else None),
            average_active_return_pct=(
                round(sum(result.pnl_pct or 0.0 for result in active) / len(active), 4)
                if active
                else None
            ),
            average_signal_return_pct=(
                round(
                    sum(result.pnl_pct or 0.0 for result in evaluated) / len(evaluated),
                    4,
                )
                if evaluated
                else None
            ),
            tracking_horizon_hours=settings.tracking_horizon_hours,
        )

    async def list_results(self, limit: int | None = None) -> list[SignalResultRead]:
        """Return recent paper-trading observations without modifying state."""
        return await self.result_store.list_results(limit or settings.tracking_scan_limit)

    async def _forward_exit_price(
        self,
        signal: SignalRead,
        now: datetime,
        frames: dict[str, pd.DataFrame],
    ) -> float | None:
        target = signal.signal_timestamp + timedelta(hours=settings.tracking_horizon_hours)
        if now < target + timedelta(hours=1):
            return None

        if signal.pair not in frames:
            frames[signal.pair] = await asyncio.to_thread(
                self.market_data.fetch_ohlcv,
                signal.pair,
                "1h",
                settings.ohlcv_exec_limit,
            )

        candles = frames[signal.pair]
        current_time = pd.Timestamp(now)
        completed = candles.index + pd.Timedelta(hours=1) <= current_time
        target_rows = candles[(candles.index >= pd.Timestamp(target)) & completed]
        if target_rows.empty:
            return None

        return float(target_rows.iloc[0]["close"])

    @staticmethod
    def _evaluate(signal: SignalRead, exit_price: float) -> tuple[str, float]:
        if signal.action == "CASH":
            return "cash", 0.0

        pnl_pct = round(((exit_price / signal.price) - 1) * 100, 6)
        if pnl_pct > 0:
            return "gain", pnl_pct
        if pnl_pct < 0:
            return "loss", pnl_pct
        return "flat", 0.0
