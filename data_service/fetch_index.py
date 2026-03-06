from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from data_service.normalize import normalize_ohlcv

try:
    import akshare as ak
except Exception:
    ak = None


_HK_INDEX_HINTS = {"HSI", "HSCEI", "HSTECH", "HSAHP", "HSCCI"}


def _sina_symbol(symbol: str) -> list[str]:
    return [f"sh{symbol}", f"sz{symbol}", symbol]


def _is_hk_index_symbol(symbol: str) -> bool:
    text = str(symbol).upper()
    if text in _HK_INDEX_HINTS:
        return True
    return any(char.isalpha() for char in text)


def _clip_date_range(frame: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty or "date" not in frame.columns:
        return frame

    start = pd.to_datetime(start_date, errors="coerce")
    end = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return frame

    table = frame.copy()
    date_series = pd.to_datetime(table["date"], errors="coerce")
    mask = (date_series >= start) & (date_series <= end)
    return table.loc[mask].reset_index(drop=True)


def _fetch_hk_index_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    if ak is None:
        return None

    normalized_symbol = str(symbol).upper()
    function_names = ["stock_hk_index_daily_em", "stock_hk_index_daily_sina"]

    for function_name in function_names:
        function = getattr(ak, function_name, None)
        if not callable(function):
            continue

        try:
            raw = function(symbol=normalized_symbol)
            if raw is None or raw.empty:
                continue
            normalized = normalize_ohlcv(raw, symbol=symbol)
            if normalized.empty:
                continue
            return _clip_date_range(normalized, start_date=start_date, end_date=end_date)
        except Exception:
            continue

    return None


def fetch_index_history(symbol: str, start_date: str = "20050101", end_date: str | None = None) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for data fetching")

    end = end_date or datetime.now().strftime("%Y%m%d")
    errors: list[str] = []

    if _is_hk_index_symbol(symbol):
        hk_frame = _fetch_hk_index_history(symbol=symbol, start_date=start_date, end_date=end)
        if hk_frame is not None and not hk_frame.empty:
            return hk_frame

    try:
        generic_df = ak.index_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end,
        )
        if generic_df is not None and not generic_df.empty:
            normalized = normalize_ohlcv(generic_df, symbol=symbol)
            return _clip_date_range(normalized, start_date=start_date, end_date=end)
    except Exception as exc:
        errors.append(str(exc))

    for sina_symbol in _sina_symbol(symbol):
        try:
            daily_df = ak.stock_zh_index_daily(symbol=sina_symbol)
            if daily_df is not None and not daily_df.empty:
                normalized = normalize_ohlcv(daily_df, symbol=symbol)
                return _clip_date_range(normalized, start_date=start_date, end_date=end)
        except Exception as exc:
            errors.append(str(exc))

    joined = " | ".join(errors[-3:])
    raise RuntimeError(f"failed to fetch index {symbol}: {joined}")


def fetch_index_batch(symbols: Sequence[str], start_date: str = "20050101", end_date: str | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        try:
            frame = fetch_index_history(symbol=symbol, start_date=start_date, end_date=end_date)
            frames.append(frame)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "symbol"])

    return pd.concat(frames, ignore_index=True)
