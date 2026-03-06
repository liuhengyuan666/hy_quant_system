from __future__ import annotations

from typing import Iterable

import pandas as pd

SUPPORTED_EOD_FREQUENCIES = ("D", "W", "M")


def normalize_bar_frequency(value: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in SUPPORTED_EOD_FREQUENCIES:
        raise ValueError(f"unsupported EOD frequency: {value}")
    return normalized


def normalize_bar_frequencies(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return list(SUPPORTED_EOD_FREQUENCIES)

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_bar_frequency(value)
        if normalized not in seen:
            ordered.append(normalized)
            seen.add(normalized)
    return ordered or list(SUPPORTED_EOD_FREQUENCIES)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()

    table = frame.copy()
    table["date"] = pd.to_datetime(table["date"], errors="coerce")
    for column in ["open", "high", "low", "close", "volume"]:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    table = table.dropna(subset=["date", "open", "high", "low", "close"])
    if table.empty:
        return _empty_frame()
    table["volume"] = table["volume"].fillna(0.0)
    return table.sort_values("date").reset_index(drop=True)


def resample_ohlcv(frame: pd.DataFrame, frequency: str) -> pd.DataFrame:
    normalized = normalize_bar_frequency(frequency)
    table = _prepare_frame(frame)
    if table.empty or normalized == "D":
        if table.empty:
            return table
        table["date"] = table["date"].dt.date
        return table.reset_index(drop=True)

    if normalized == "W":
        bucket = table["date"].dt.to_period("W-FRI")
    else:
        bucket = table["date"].dt.to_period("M")

    grouped = table.groupby(bucket, sort=True)
    result = grouped.agg(
        symbol=("symbol", "last"),
        date=("date", "max"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    result = result.reset_index(drop=True)
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.date
    return result[["symbol", "date", "open", "high", "low", "close", "volume"]]
