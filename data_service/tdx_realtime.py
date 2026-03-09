from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import pandas as pd

try:
    from pytdx.config.hosts import hq_hosts
    from pytdx.hq import TdxHq_API
    from pytdx.params import TDXParams
except Exception:
    hq_hosts = []
    TdxHq_API = None
    TDXParams = None


def supports_tdx_symbol(symbol: str) -> bool:
    return str(symbol).isdigit()


def resolve_tdx_index_market(symbol: str) -> int:
    code = str(symbol)
    if not supports_tdx_symbol(code):
        raise ValueError(f"unsupported TDX index symbol: {symbol}")
    return 0 if code.startswith("399") else 1


def resolve_tdx_security_market(symbol: str) -> int:
    code = str(symbol)
    if not supports_tdx_symbol(code):
        raise ValueError(f"unsupported TDX security symbol: {symbol}")
    if code.startswith(("5", "6")):
        return 1
    if code.startswith(("0", "1", "3")):
        return 0
    raise ValueError(f"unable to resolve TDX market for symbol: {symbol}")


def _empty_realtime_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"])


def _float_series(frame: pd.DataFrame, column: str, default: float | None = None) -> pd.Series:
    if column not in frame.columns:
        fill_value = float("nan") if default is None else float(default)
        return pd.Series([fill_value] * len(frame.index), dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _normalize_tdx_bars(rows: Iterable[dict[str, object]], symbol: str, bar_frequency: str) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        return _empty_realtime_bars()

    timestamp_source = "datetime" if "datetime" in frame.columns else None
    if timestamp_source is None and all(column in frame.columns for column in ["year", "month", "day", "hour", "minute"]):
        frame["datetime"] = (
            frame["year"].astype(int).astype(str).str.zfill(4)
            + "-"
            + frame["month"].astype(int).astype(str).str.zfill(2)
            + "-"
            + frame["day"].astype(int).astype(str).str.zfill(2)
            + " "
            + frame["hour"].astype(int).astype(str).str.zfill(2)
            + ":"
            + frame["minute"].astype(int).astype(str).str.zfill(2)
            + ":00"
        )
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
        timestamp_source = "datetime"
    if timestamp_source is None:
        raise ValueError(f"missing datetime columns for symbol {symbol}")

    normalized = pd.DataFrame(
        {
            "ts": pd.to_datetime(frame[timestamp_source], errors="coerce"),
            "open": _float_series(frame, "open"),
            "high": _float_series(frame, "high"),
            "low": _float_series(frame, "low"),
            "close": _float_series(frame, "close"),
            "volume": _float_series(frame, "vol", default=0.0).fillna(0.0),
        }
    )
    normalized = normalized.dropna(subset=["ts", "open", "high", "low", "close"])
    if normalized.empty:
        return _empty_realtime_bars()
    normalized["symbol"] = str(symbol)
    normalized["bar_frequency"] = str(bar_frequency)
    normalized["source"] = "pytdx"
    return normalized[["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"]].drop_duplicates(subset=["ts"], keep="last").sort_values("ts").reset_index(drop=True)


@lru_cache(maxsize=1)
def _resolve_tdx_host() -> tuple[str, int]:
    if TdxHq_API is None or TDXParams is None:
        raise ImportError("pytdx is required for TDX realtime fetching")

    for _, host, port in hq_hosts:
        api = TdxHq_API(heartbeat=False)
        try:
            if api.connect(host, port, time_out=3):
                api.disconnect()
                return host, port
        except Exception:
            continue
    raise ConnectionError("no reachable TDX quote host found")


def _fetch_with_tdx(symbol: str, bar_frequency: str, *, is_index: bool) -> pd.DataFrame:
    if TdxHq_API is None or TDXParams is None:
        raise ImportError("pytdx is required for TDX realtime fetching")

    last_error: Exception | None = None
    for attempt in range(2):
        if attempt > 0:
            _resolve_tdx_host.cache_clear()
        host, port = _resolve_tdx_host()
        api = TdxHq_API(heartbeat=False)
        try:
            if not api.connect(host, port, time_out=3):
                raise ConnectionError(f"failed to connect TDX host {host}:{port}")
            if is_index:
                market = resolve_tdx_index_market(symbol)
                rows = api.get_index_bars(TDXParams.KLINE_TYPE_5MIN, market, str(symbol), 0, 120)
            else:
                market = resolve_tdx_security_market(symbol)
                rows = api.get_security_bars(TDXParams.KLINE_TYPE_5MIN, market, str(symbol), 0, 120)
            return _normalize_tdx_bars(rows or [], symbol=str(symbol), bar_frequency=bar_frequency)
        except Exception as exc:
            last_error = exc
        finally:
            try:
                api.disconnect()
            except Exception:
                pass

    if last_error is not None:
        raise last_error
    raise ConnectionError(f"unable to fetch TDX realtime bars for {symbol}")


def fetch_tdx_index_bars(symbol: str, period: str = "5") -> pd.DataFrame:
    if str(period) != "5":
        raise ValueError("pytdx intraday integration currently supports 5-minute bars only")
    return _fetch_with_tdx(symbol=str(symbol), bar_frequency=str(period), is_index=True)


def fetch_tdx_security_bars(symbol: str, period: str = "5") -> pd.DataFrame:
    if str(period) != "5":
        raise ValueError("pytdx intraday integration currently supports 5-minute bars only")
    return _fetch_with_tdx(symbol=str(symbol), bar_frequency=str(period), is_index=False)
