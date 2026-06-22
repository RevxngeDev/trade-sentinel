from __future__ import annotations

import ccxt
import pandas as pd

from app.config import settings


class MarketDataError(Exception):
    pass


class MarketDataService:
    def __init__(self, exchange_id: str | None = None) -> None:
        self.exchange_id = exchange_id or settings.exchange_id
        self.exchange = self._build_exchange(self.exchange_id)

    @staticmethod
    def _build_exchange(exchange_id: str):
        try:
            exchange_class = getattr(ccxt, exchange_id)
        except AttributeError as exc:
            raise MarketDataError(f"Exchange not supported: {exchange_id}") from exc

        return exchange_class(
            {
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        clean_symbol = symbol.strip().upper()

        if "/" in clean_symbol:
            return clean_symbol

        if clean_symbol.endswith("USDT"):
            base = clean_symbol.replace("USDT", "")
            return f"{base}/USDT"

        if clean_symbol.endswith("USD"):
            base = clean_symbol.replace("USD", "")
            return f"{base}/USD"

        raise MarketDataError(
            f"Invalid symbol format: {symbol}. Use BTCUSDT or BTC/USDT."
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "4h",
        limit: int = 600,
    ) -> pd.DataFrame:
        normalized_symbol = self.normalize_symbol(symbol)

        try:
            rows = self.exchange.fetch_ohlcv(
                symbol=normalized_symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception as exc:
            raise MarketDataError(
                f"Could not fetch OHLCV for {normalized_symbol}: {exc}"
            ) from exc

        if not rows:
            raise MarketDataError(f"No OHLCV data returned for {normalized_symbol}.")

        df = pd.DataFrame(
            rows,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms",
            utc=True,
        )

        df = df.set_index("timestamp").sort_index()

        return df