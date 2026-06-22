"""Signal generation and Supabase HTTP persistence orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.config import settings
from app.schemas.regime import RegimeResponse, SignalRead
from app.services.market_data import MarketDataService
from app.services.regime_service import RegimeService
from app.services.signal_store import SignalStore, SupabaseSignalStore


class SignalService:
    def __init__(
        self,
        market_data: MarketDataService | None = None,
        regime_service: RegimeService | None = None,
        store: SignalStore | None = None,
    ) -> None:
        self.market_data = market_data or MarketDataService()
        self.regime_service = regime_service or RegimeService()
        self.store = store or SupabaseSignalStore()

    async def generate(self, symbol: str) -> RegimeResponse:
        ohlcv_4h, ohlcv_1h = await asyncio.gather(
            asyncio.to_thread(
                self.market_data.fetch_ohlcv,
                symbol,
                settings.regime_base_timeframe,
                settings.ohlcv_limit,
            ),
            asyncio.to_thread(
                self.market_data.fetch_ohlcv,
                symbol,
                settings.regime_exec_timeframe,
                settings.ohlcv_exec_limit,
            ),
        )
        normalized_symbol = self.market_data.normalize_symbol(symbol)
        return self.regime_service.analyze(
            symbol=normalized_symbol,
            ohlcv_1h=ohlcv_1h,
            ohlcv_4h=ohlcv_4h,
        )

    async def persist(self, response: RegimeResponse) -> SignalRead | None:
        """Store a signal once per pair and execution candle."""
        return await self.store.insert_if_absent(self._to_payload(response))

    async def get_by_candle(
        self, pair: str, signal_timestamp: datetime
    ) -> SignalRead | None:
        return await self.store.get_by_candle(pair, signal_timestamp)

    async def list_signals(
        self, pair: str | None, limit: int
    ) -> list[SignalRead]:
        return await self.store.list_signals(pair, limit)

    async def generate_and_store(
        self, symbol: str
    ) -> tuple[RegimeResponse, SignalRead | None]:
        response = await self.generate(symbol)
        stored = await self.persist(response)
        return response, stored

    @staticmethod
    def _to_payload(response: RegimeResponse) -> dict:
        return {
            "pair": response.symbol,
            "timeframe": response.timeframe,
            "action": response.action,
            "regime_on": response.regime_on,
            "previous_regime_on": response.previous_regime_on,
            "confidence": response.confidence,
            "price": response.price,
            "signal_timestamp": response.timestamp.isoformat(),
            "decision_timestamp": response.decision_timestamp.isoformat(),
            "conditions": response.conditions.model_dump(),
            "indicators": response.indicators.model_dump(),
            "reasoning": response.reasoning,
        }
