from __future__ import annotations

from typing import Sequence

import pandas as pd

from config.settings import load_runtime_config
from data_service.akshare_runtime import disable_requests_env_proxy
from data_service.futu_realtime import fetch_futu_intraday_bars, supports_futu_symbol
from data_service.normalize_realtime import normalize_realtime_bars, normalize_realtime_snapshot
from data_service.tdx_realtime import fetch_tdx_index_bars, supports_tdx_symbol

try:
    import akshare as ak
except Exception:
    ak = None


def fetch_realtime_index_snapshots(symbols: Sequence[str]) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")

    frames: list[pd.DataFrame] = []
    em_groups = ["沪深重要指数", "上证系列指数", "深证系列指数", "中证系列指数"]
    with disable_requests_env_proxy():
        for group in em_groups:
            try:
                raw = ak.stock_zh_index_spot_em(symbol=group)
                frames.append(raw)
            except Exception:
                continue
        try:
            frames.append(ak.stock_zh_index_spot_sina())
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(columns=["ts", "symbol", "price", "open", "high", "low", "prev_close", "volume"])
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代码"], keep="last")
    return normalize_realtime_snapshot(merged, list(symbols))


def fetch_intraday_index_bars(symbol: str, period: str = "5") -> pd.DataFrame:
    if supports_tdx_symbol(symbol):
        try:
            return fetch_tdx_index_bars(symbol=symbol, period=period)
        except Exception:
            pass
    runtime = load_runtime_config()
    if supports_futu_symbol(symbol, runtime_config=runtime):
        return fetch_futu_intraday_bars(symbol=symbol, period=period, runtime_config=runtime)
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    with disable_requests_env_proxy():
        raw = ak.index_zh_a_hist_min_em(symbol=symbol, period=period)
    return normalize_realtime_bars(raw, symbol=symbol, bar_frequency=period)
