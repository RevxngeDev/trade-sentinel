"""
Indicadores técnicos — fuente única de verdad.

Implementación hand-rolled (ewm), sin pandas-ta, para que backtest y app
calculen EXACTAMENTE los mismos valores y no haya divergencia entre lo
validado y lo que sirve la API. Ver docs/ai-context/DECISIONS.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_ema(df: pd.DataFrame, period: int) -> pd.DataFrame:
    # min_periods=period: el EMA es NaN hasta tener historia suficiente, en vez
    # de seedear con pocas velas. Evita un EMA200 mal "calentado" en las
    # primeras ~200 velas (que desplazaba el inicio del dataset en el backtest).
    df[f"ema_{period}"] = df["close"].ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()
    return df


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df[f"rsi_{period}"] = 100 - (100 / (1 + rs))
    df[f"rsi_{period}"] = df[f"rsi_{period}"].fillna(50)

    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    previous_close = df["close"].shift(1)

    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df[f"atr_{period}"] = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    return df


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in ["open", "high", "low", "close", "volume"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def add_core_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Indicadores mínimos para el régimen: EMA 20/50/200, RSI 14, ATR 14.
    Usado por la API (RegimeService) y por los scripts de régimen del backtest.
    """
    df = _coerce_numeric(df)

    df = add_ema(df, 20)
    df = add_ema(df, 50)
    df = add_ema(df, 200)
    df = add_rsi(df, 14)
    df = add_atr(df, 14)

    return df.dropna(subset=["close", "ema_50", "ema_200", "rsi_14"])
