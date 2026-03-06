from __future__ import annotations

from typing import Sequence

import pandas as pd

from data_service.normalize_realtime import normalize_realtime_bars, normalize_realtime_snapshot

try:
    import akshare as ak
except Exception:
    ak = None


def fetch_realtime_etf_snapshots(symbols: Sequence[str]) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    raw = ak.fund_etf_spot_em()
    return normalize_realtime_snapshot(raw, list(symbols))


def fetch_intraday_etf_bars(symbol: str, period: str = "5") -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    raw = ak.fund_etf_hist_min_em(symbol=symbol, period=period, adjust="")
    return normalize_realtime_bars(raw, symbol=symbol, bar_frequency=period)
