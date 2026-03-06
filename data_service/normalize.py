from __future__ import annotations

import pandas as pd


_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "date": ["date", "日期", "时间"],
    "open": ["open", "开盘"],
    "high": ["high", "最高"],
    "low": ["low", "最低"],
    "close": ["close", "收盘", "最新价"],
    "volume": ["volume", "成交量", "成交量(手)", "amount", "成交额"],
}


def normalize_ohlcv(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "symbol"])

    frame = raw.copy()
    rename_map: dict[str, str] = {}

    for target, names in _COLUMN_CANDIDATES.items():
        for candidate in names:
            if candidate in frame.columns:
                rename_map[candidate] = target
                break

    frame = frame.rename(columns=rename_map)

    if "date" not in frame.columns:
        index_name = str(frame.index.name).lower() if frame.index.name else ""
        if "date" in index_name or "日期" in index_name or "时间" in index_name:
            frame = frame.reset_index().rename(columns={frame.index.name: "date"})
        else:
            frame = frame.reset_index(drop=False)
            frame = frame.rename(columns={frame.columns[0]: "date"})

    for col in ["open", "high", "low", "close"]:
        if col not in frame.columns:
            raise ValueError(f"missing required column {col} for symbol {symbol}")

    if "volume" not in frame.columns:
        frame["volume"] = 0

    frame = frame[["date", "open", "high", "low", "close", "volume"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame = frame.dropna(subset=["date", "open", "high", "low", "close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    frame["symbol"] = symbol
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    return frame.sort_values("date").reset_index(drop=True)
