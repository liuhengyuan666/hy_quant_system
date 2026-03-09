from __future__ import annotations

import socket

import pandas as pd

from config.settings import RuntimeConfig, load_runtime_config

try:
    from futu import AuType, KLType, OpenQuoteContext, RET_OK, SubType
except Exception:
    AuType = None
    KLType = None
    OpenQuoteContext = None
    RET_OK = None
    SubType = None


def supports_futu_symbol(symbol: str, runtime_config: RuntimeConfig | None = None) -> bool:
    config = runtime_config or load_runtime_config()
    return config.hk_realtime_provider == "futu" and str(symbol) in (config.hk_realtime_futu_symbol_map or {})


def _assert_futu_opend_reachable(host: str, port: int, timeout: float = 1.0) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        return None


def _empty_realtime_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"])


def _normalize_futu_kline(frame: pd.DataFrame, symbol: str, bar_frequency: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_realtime_bars()

    normalized = pd.DataFrame(
        {
            "ts": pd.to_datetime(frame["time_key"], errors="coerce"),
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "volume": pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0),
        }
    )
    normalized = normalized.dropna(subset=["ts", "open", "high", "low", "close"])
    if normalized.empty:
        return _empty_realtime_bars()
    normalized["symbol"] = str(symbol)
    normalized["bar_frequency"] = str(bar_frequency)
    normalized["source"] = "futu"
    return normalized[["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"]].drop_duplicates(subset=["ts"], keep="last").sort_values("ts").reset_index(drop=True)


def fetch_futu_intraday_bars(symbol: str, period: str = "5", runtime_config: RuntimeConfig | None = None) -> pd.DataFrame:
    config = runtime_config or load_runtime_config()
    if config.hk_realtime_provider != "futu":
        raise ValueError("Futu HK realtime provider is not enabled")
    if OpenQuoteContext is None or SubType is None or KLType is None or AuType is None or RET_OK is None:
        raise ImportError("futu-api is required for Futu realtime fetching")
    if str(period) != "5":
        raise ValueError("Futu HK realtime integration currently supports 5-minute bars only")

    symbol_map = config.hk_realtime_futu_symbol_map or {}
    provider_code = symbol_map.get(str(symbol))
    if not provider_code:
        raise ValueError(f"missing Futu code mapping for symbol: {symbol}")

    _assert_futu_opend_reachable(config.hk_realtime_futu_host, config.hk_realtime_futu_port)

    quote_ctx = OpenQuoteContext(
        host=config.hk_realtime_futu_host,
        port=config.hk_realtime_futu_port,
        is_encrypt=config.hk_realtime_futu_is_encrypt,
    )
    try:
        ret, data = quote_ctx.subscribe([provider_code], [SubType.K_5M], subscribe_push=False)
        if ret != RET_OK:
            raise ConnectionError(f"Futu subscribe failed for {provider_code}: {data}")

        ret, frame = quote_ctx.get_cur_kline(provider_code, 120, KLType.K_5M, AuType.NONE)
        if ret != RET_OK:
            raise ConnectionError(f"Futu get_cur_kline failed for {provider_code}: {frame}")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"unexpected Futu kline payload for {provider_code}: {type(frame).__name__}")
        return _normalize_futu_kline(frame, symbol=str(symbol), bar_frequency=str(period))
    finally:
        quote_ctx.close()
