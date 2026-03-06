from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from config.settings import PostgresConfig
from data_storage.database import session_scope
from data_storage.repository import (
    load_market_prices_map,
    upsert_technical_indicators,
)

try:
    import talib
except Exception:
    talib = None


def _macd_with_pandas(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist


def _rsi_with_pandas(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_symbol_indicators(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(columns=["symbol", "date", "ma20", "ma60", "macd", "macd_signal", "macd_hist", "rsi"])

    frame = data.sort_values("date").copy()
    close = frame["close"].astype(float)

    if talib is not None:
        close_np = close.to_numpy(dtype=float)
        ma20 = pd.Series(talib.MA(close_np, timeperiod=20), index=frame.index)
        ma60 = pd.Series(talib.MA(close_np, timeperiod=60), index=frame.index)
        macd_np, macd_signal_np, macd_hist_np = talib.MACD(close_np, fastperiod=12, slowperiod=26, signalperiod=9)
        macd = pd.Series(macd_np, index=frame.index)
        macd_signal = pd.Series(macd_signal_np, index=frame.index)
        macd_hist = pd.Series(macd_hist_np, index=frame.index)
        rsi = pd.Series(talib.RSI(close_np, timeperiod=14), index=frame.index)
    else:
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        macd, macd_signal, macd_hist = _macd_with_pandas(close)
        rsi = _rsi_with_pandas(close)

    result = pd.DataFrame(
        {
            "symbol": frame["symbol"].astype(str).to_list(),
            "date": pd.to_datetime(frame["date"]).dt.date,
            "ma20": ma20,
            "ma60": ma60,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "rsi": rsi,
        }
    )
    return result


def compute_indicators_table(price_data: pd.DataFrame) -> pd.DataFrame:
    if price_data.empty:
        return pd.DataFrame(columns=["symbol", "date", "ma20", "ma60", "macd", "macd_signal", "macd_hist", "rsi"])

    tables: list[pd.DataFrame] = []
    for _, group in price_data.groupby("symbol", sort=False):
        table = compute_symbol_indicators(group)
        tables.append(table)
    merged = pd.concat(tables, ignore_index=True)
    merged = merged.replace([np.inf, -np.inf], np.nan)
    return merged.dropna(subset=["ma20", "ma60", "macd", "rsi"], how="all")


def refresh_technical_indicators(
    symbols: Sequence[str],
    lookback: int = 900,
    config: PostgresConfig | None = None,
) -> int:
    with session_scope(config) as session:
        data_by_symbol = load_market_prices_map(session, symbols, limit=lookback)
        rows_written = 0
        for symbol, frame in data_by_symbol.items():
            if frame.empty:
                continue
            if "symbol" not in frame.columns:
                frame = frame.copy()
                frame["symbol"] = symbol
            indicators = compute_symbol_indicators(frame)
            rows_written += upsert_technical_indicators(session, indicators.to_dict("records"))
        return rows_written
