"""Signal generation and Supabase HTTP persistence orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.config import settings
from app.schemas.regime import BackfillRunRead, RegimeResponse, SignalRead
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

    async def get_by_id(self, signal_id: int) -> SignalRead | None:
        return await self.store.get_by_id(signal_id)

    async def generate_and_store(
        self, symbol: str
    ) -> tuple[RegimeResponse, SignalRead | None]:
        response = await self.generate(symbol)
        stored = await self.persist(response)
        return response, stored

    async def backfill(
        self,
        symbol: str,
        *,
        since: datetime | None = None,
        now: datetime | None = None,
        lookback_days: int | None = None,
    ) -> BackfillRunRead:
        """
        Rellena las señales de las fronteras de 4h que falten (p.ej. tras un
        apagón del backend). Reconstruye cada señal pasada cortando los OHLCV
        hasta esa vela y usando el MISMO pipeline `analyze` (indicadores
        causales => idéntico a lo que se habría capturado en vivo). Idempotente.
        """
        now = now or datetime.now(timezone.utc)

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
        existing = await self.store.list_signals(
            normalized_symbol, settings.tracking_scan_limit
        )
        existing_ts = {signal.signal_timestamp for signal in existing}

        if since is None:
            if existing_ts:
                since = min(existing_ts)
            else:
                days = (
                    lookback_days
                    if lookback_days is not None
                    else settings.backfill_lookback_days
                )
                since = now - timedelta(days=days)

        slots = self._four_hour_slots(ohlcv_1h.index, since=since, now=now)

        scanned = created = skipped_existing = skipped_insufficient = 0
        for slot in slots:
            scanned += 1
            if slot.to_pydatetime() in existing_ts:
                skipped_existing += 1
                continue

            df_1h = ohlcv_1h[ohlcv_1h.index <= slot]
            df_4h = ohlcv_4h[ohlcv_4h.index <= slot]

            try:
                response = self.regime_service.analyze(
                    symbol=normalized_symbol,
                    ohlcv_1h=df_1h,
                    ohlcv_4h=df_4h,
                )
            except ValueError:
                # Aún no hay suficiente historia (EMA200) para esa vela.
                skipped_insufficient += 1
                continue

            stored = await self.persist(response)
            if stored is not None:
                created += 1
                existing_ts.add(slot.to_pydatetime())
            else:
                skipped_existing += 1

        return BackfillRunRead(
            scanned=scanned,
            created=created,
            skipped_existing=skipped_existing,
            skipped_insufficient=skipped_insufficient,
            first_slot=slots[0].to_pydatetime() if slots else None,
            last_slot=slots[-1].to_pydatetime() if slots else None,
        )

    @staticmethod
    def _four_hour_slots(
        index: pd.DatetimeIndex,
        *,
        since: datetime,
        now: datetime,
    ) -> list[pd.Timestamp]:
        """Velas 1h en fronteras de 4h (00/04/08/12/16/20), cerradas, desde `since`."""
        since_ts = pd.Timestamp(since)
        now_ts = pd.Timestamp(now)

        slots: list[pd.Timestamp] = []
        for timestamp in index:
            if timestamp.hour % 4 != 0 or timestamp.minute != 0:
                continue
            if timestamp < since_ts:
                continue
            if timestamp + pd.Timedelta(hours=1) > now_ts:
                # La vela aún no ha cerrado: la captura el scheduler en vivo.
                continue
            slots.append(timestamp)
        return slots

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
