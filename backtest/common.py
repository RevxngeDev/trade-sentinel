"""
Infraestructura compartida del backtest: constantes, descarga y carga de datos.

Los indicadores se calculan con la fuente única (app.core.indicators), de modo
que el backtest y la API usan exactamente la misma implementación.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import ccxt
import pandas as pd

from app.core.indicators import add_core_indicators


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

EXCHANGE_ID = "binance"
INITIAL_CASH = 1000
FEES = 0.001  # 0.1% por operación aproximado


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    years: int = 2,
    exchange_id: str = EXCHANGE_ID,
) -> pd.DataFrame:
    """
    Descarga OHLCV histórico desde Binance usando ccxt.
    Solo lectura de datos, no usa API keys ni ejecuta operaciones.
    """
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    since_dt = datetime.now(timezone.utc) - timedelta(days=365 * years)
    since = int(since_dt.timestamp() * 1000)

    all_rows: list[Any] = []
    limit = 1000

    print(f"Descargando {symbol} {timeframe} desde {since_dt.date()}...")

    while True:
        rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)

        if not rows:
            break

        all_rows.extend(rows)
        since = rows[-1][0] + 1
        print(f"Velas descargadas: {len(all_rows)}")

        if len(rows) < limit:
            break

        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(
        all_rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()

    return df


def symbol_to_filename(symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "_")
    return DATA_DIR / f"{safe_symbol}_{timeframe}.csv"


def load_pair_data(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga 1h y 4h para un símbolo, con indicadores ya calculados.
    Si el CSV local existe lo usa; si no, descarga vía ccxt (solo lectura).
    """
    df_1h_path = symbol_to_filename(symbol, "1h")
    df_4h_path = symbol_to_filename(symbol, "4h")

    if df_1h_path.exists():
        df_1h = pd.read_csv(df_1h_path, parse_dates=["timestamp"], index_col="timestamp")
    else:
        df_1h = fetch_ohlcv(symbol, "1h", years=2)
        df_1h.to_csv(df_1h_path)

    if df_4h_path.exists():
        df_4h = pd.read_csv(df_4h_path, parse_dates=["timestamp"], index_col="timestamp")
    else:
        df_4h = fetch_ohlcv(symbol, "4h", years=2)
        df_4h.to_csv(df_4h_path)

    return add_core_indicators(df_1h), add_core_indicators(df_4h)
