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

__all__ = [
    "DATA_DIR",
    "EXCHANGE_ID",
    "FEES",
    "FROZEN_DATA_DIR",
    "INITIAL_CASH",
    "fetch_ohlcv",
    "generate_walk_forward_windows",
    "load_pair_data",
    "symbol_to_filename",
]


DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Copia congelada del dataset con el que se validó la estrategia (BTC hasta
# 2026-06-11, resto hasta 2026-06-30). Los CSV de DATA_DIR se refrescan; estos
# NO, para que las guardas de regresión sigan comparando contra lo documentado.
FROZEN_DATA_DIR = DATA_DIR / "frozen"

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


def symbol_to_filename(
    symbol: str,
    timeframe: str,
    data_dir: Path = DATA_DIR,
) -> Path:
    safe_symbol = symbol.replace("/", "_")
    return data_dir / f"{safe_symbol}_{timeframe}.csv"


def load_pair_data(
    symbol: str,
    *,
    refresh: bool = False,
    years: int = 2,
    data_dir: Path = DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga 1h y 4h para un símbolo, con indicadores ya calculados.
    Si el CSV local existe lo usa; si no, descarga vía ccxt (solo lectura).

    `refresh=True` fuerza la re-descarga y sobreescribe el CSV cacheado. Los CSV
    se quedan congelados en la fecha de su descarga, así que hace falta refrescar
    para evaluar periodos recientes.

    `data_dir=FROZEN_DATA_DIR` lee el dataset congelado de la validación original
    (nunca se refresca; lo usan las guardas de regresión).
    """
    frames: list[pd.DataFrame] = []

    for timeframe in ("1h", "4h"):
        path = symbol_to_filename(symbol, timeframe, data_dir)

        if path.exists() and not refresh:
            df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
        else:
            df = fetch_ohlcv(symbol, timeframe, years=years)
            df.to_csv(path)

        frames.append(add_core_indicators(df))

    return frames[0], frames[1]


def generate_walk_forward_windows(
    df_1h: pd.DataFrame,
    *,
    train_days: int = 270,
    test_days: int = 60,
) -> list[dict[str, Any]]:
    """
    Ventanas rodantes train/test. El train avanza `test_days` cada fold, de modo
    que las ventanas de TEST son contiguas y no se solapan (se pueden componer).

    Compartido por el walk-forward de BTC y el multi-activo para que ambos usen
    exactamente el mismo troceado temporal.
    """
    start = df_1h.index.min()
    end = df_1h.index.max()

    windows: list[dict[str, Any]] = []
    train_start = start
    fold = 1

    while True:
        train_end = train_start + pd.Timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + pd.Timedelta(days=test_days)

        if test_end > end:
            break

        windows.append(
            {
                "fold": fold,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )

        train_start = train_start + pd.Timedelta(days=test_days)
        fold += 1

    return windows
