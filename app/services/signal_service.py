"""
SignalService: orquesta la generación de la señal y su persistencia.

- `generate`: descarga 4h+1h y produce el RegimeResponse (pipeline validado).
- `persist`: guarda la señal evitando duplicados por (par, vela de ejecución).
- `generate_and_store`: ambas, para el endpoint de captura y el scheduler.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.signal import Signal
from app.schemas.regime import RegimeResponse
from app.services.market_data import MarketDataService
from app.services.regime_service import RegimeService


class SignalService:
    def __init__(
        self,
        market_data: MarketDataService | None = None,
        regime_service: RegimeService | None = None,
    ) -> None:
        self.market_data = market_data or MarketDataService()
        self.regime_service = regime_service or RegimeService()

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

    async def persist(
        self,
        session: AsyncSession,
        response: RegimeResponse,
    ) -> Signal | None:
        """Persiste la señal. Devuelve None si ya existía para esa vela."""
        existing = await session.scalar(
            select(Signal).where(
                Signal.pair == response.symbol,
                Signal.signal_timestamp == response.timestamp,
            )
        )
        if existing is not None:
            return None

        signal = self._to_model(response)
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        return signal

    async def generate_and_store(
        self,
        session: AsyncSession,
        symbol: str,
    ) -> tuple[RegimeResponse, Signal | None]:
        response = await self.generate(symbol)
        stored = await self.persist(session, response)
        return response, stored

    @staticmethod
    def _to_model(response: RegimeResponse) -> Signal:
        return Signal(
            pair=response.symbol,
            timeframe=response.timeframe,
            action=response.action,
            regime_on=response.regime_on,
            previous_regime_on=response.previous_regime_on,
            confidence=response.confidence,
            price=response.price,
            signal_timestamp=response.timestamp,
            decision_timestamp=response.decision_timestamp,
            conditions=response.conditions.model_dump(),
            indicators=response.indicators.model_dump(),
            reasoning=response.reasoning,
        )
