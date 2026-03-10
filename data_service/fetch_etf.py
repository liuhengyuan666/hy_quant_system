from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from data_service.akshare_runtime import disable_requests_env_proxy
from data_service.normalize import normalize_ohlcv

try:
    import akshare as ak
except Exception:
    ak = None


def fetch_etf_history(
    symbol: str,
    start_date: str = "20050101",
    end_date: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for data fetching")

    end = end_date or datetime.now().strftime("%Y%m%d")
    with disable_requests_env_proxy():
        raw = ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end,
            adjust=adjust,
        )
    return normalize_ohlcv(raw, symbol=symbol)


def fetch_etf_batch(
    symbols: Sequence[str],
    start_date: str = "20050101",
    end_date: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        try:
            frame = fetch_etf_history(symbol=symbol, start_date=start_date, end_date=end_date, adjust=adjust)
            frames.append(frame)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "symbol"])

    return pd.concat(frames, ignore_index=True)
