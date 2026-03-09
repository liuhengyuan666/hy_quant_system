from __future__ import annotations

from typing import Sequence

import pandas as pd

from data_service.akshare_runtime import disable_requests_env_proxy
from data_service.normalize_realtime import normalize_realtime_bars, normalize_realtime_snapshot
from data_service.tdx_realtime import fetch_tdx_security_bars, supports_tdx_symbol

try:
    import akshare as ak
except Exception:
    ak = None


def fetch_realtime_etf_snapshots(symbols: Sequence[str]) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    with disable_requests_env_proxy():
        raw = ak.fund_etf_spot_em()
    return normalize_realtime_snapshot(raw, list(symbols))


def fetch_intraday_etf_bars(symbol: str, period: str = "5") -> pd.DataFrame:
    if supports_tdx_symbol(symbol):
        try:
            return fetch_tdx_security_bars(symbol=symbol, period=period)
        except Exception:
            pass
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    with disable_requests_env_proxy():
        raw = ak.fund_etf_hist_min_em(symbol=symbol, period=period, adjust="")
    return normalize_realtime_bars(raw, symbol=symbol, bar_frequency=period)
