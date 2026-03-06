from __future__ import annotations

from datetime import datetime

import pandas as pd


def normalize_realtime_bars(raw: pd.DataFrame, symbol: str, bar_frequency: str, timestamp_col: str = "时间") -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"])

    frame = raw.copy()
    rename_map = {
        timestamp_col: "ts",
        "时间": "ts",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "最新价": "close",
        "成交量": "volume",
        "成交额": "volume",
        "date": "ts",
    }
    frame = frame.rename(columns={key: value for key, value in rename_map.items() if key in frame.columns})
    for column in ["open", "high", "low", "close"]:
        if column not in frame.columns:
            raise ValueError(f"missing required realtime column {column} for symbol {symbol}")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    if "ts" not in frame.columns:
        raise ValueError(f"missing required realtime timestamp column for symbol {symbol}")

    frame = frame[["ts", "open", "high", "low", "close", "volume"]].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    frame["symbol"] = symbol
    frame["bar_frequency"] = str(bar_frequency)
    frame["source"] = "akshare"
    return frame.drop_duplicates(subset=["ts"], keep="last").sort_values("ts").reset_index(drop=True)


def normalize_realtime_snapshot(raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ts", "symbol", "price", "open", "high", "low", "prev_close", "volume"])

    frame = raw.copy()
    rename_map = {
        "代码": "symbol",
        "最新价": "price",
        "今开": "open",
        "最高": "high",
        "最低": "low",
        "昨收": "prev_close",
        "成交量": "volume",
        "更新时间": "ts",
        "数据日期": "data_date",
    }
    frame = frame.rename(columns={key: value for key, value in rename_map.items() if key in frame.columns})
    if "symbol" not in frame.columns:
        raise ValueError("missing realtime symbol column")
    frame["symbol"] = frame["symbol"].astype(str)
    frame = frame[frame["symbol"].isin(symbols)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["ts", "symbol", "price", "open", "high", "low", "prev_close", "volume"])

    if "ts" in frame.columns:
        frame["ts"] = pd.to_datetime(frame["ts"], errors="coerce")
    elif "data_date" in frame.columns:
        frame["ts"] = pd.to_datetime(frame["data_date"], errors="coerce")
    else:
        frame["ts"] = datetime.utcnow()

    for column in ["price", "open", "high", "low", "prev_close", "volume"]:
        if column not in frame.columns:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["ts", "symbol", "price", "open", "high", "low", "prev_close", "volume"]].dropna(subset=["ts", "symbol", "price"]).reset_index(drop=True)
