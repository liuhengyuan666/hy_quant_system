from __future__ import annotations

from typing import Sequence

import pandas as pd

from data_service.normalize_realtime import normalize_realtime_bars, normalize_realtime_snapshot

try:
    import akshare as ak
except Exception:
    ak = None


def fetch_realtime_index_snapshots(symbols: Sequence[str]) -> pd.DataFrame:
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")

    frames: list[pd.DataFrame] = []
    em_groups = ["沪深重要指数", "上证系列指数", "深证系列指数", "中证系列指数"]
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
    if ak is None:
        raise ImportError("akshare is required for realtime data fetching")
    raw = ak.index_zh_a_hist_min_em(symbol=symbol, period=period)
    return normalize_realtime_bars(raw, symbol=symbol, bar_frequency=period)
