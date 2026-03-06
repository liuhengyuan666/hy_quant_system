from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from config.settings import PostgresConfig, load_universe_config
from data_storage.database import init_database, session_scope
from data_storage.realtime_repository import load_intraday_signals, load_realtime_bars_map, upsert_intraday_signals
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names
from strategy_engine.base import CrossSectionalStrategy, Signal, Strategy
from strategy_engine.library import resolve_strategy_specs


def _coerce_signal_value(value: object) -> str:
    if isinstance(value, Signal):
        return str(value.value)
    return str(getattr(value, "value", value))


def _extract_numeric_score(engine: CrossSectionalStrategy, symbol: str) -> float | None:
    for attribute in ["last_scores", "last_momentum"]:
        value = getattr(engine, attribute, None)
        if isinstance(value, dict):
            score = value.get(symbol)
            if isinstance(score, (float, int)):
                return float(score)
    return None


def generate_intraday_signals(
    signal_ts: datetime,
    symbols: Sequence[str] | None = None,
    etf_symbols: Sequence[str] | None = None,
    strategy_names: Sequence[str] | None = None,
    bar_frequency: str = "5",
    lookback: int = 120,
    save: bool = True,
    config: PostgresConfig | None = None,
) -> pd.DataFrame:
    universe = load_universe_config()
    selected_symbols = list(symbols or sorted(set(universe.index_symbols + universe.etf_symbols)))
    selected_etfs = list(etf_symbols or universe.etf_symbols)
    strategy_specs = resolve_strategy_specs(strategy_names, supported_mode="intraday")

    init_database(config)
    with session_scope(config) as session:
        data_by_symbol = load_realtime_bars_map(session, selected_symbols, bar_frequency=bar_frequency, limit=lookback)
        records: list[dict[str, object]] = []

        for symbol, frame in data_by_symbol.items():
            if frame.empty:
                continue
            for spec in strategy_specs:
                if spec.mode != "single":
                    continue
                engine = spec.engine
                if not isinstance(engine, Strategy):
                    continue
                records.append(
                    {
                        "ts": signal_ts,
                        "symbol": symbol,
                        "strategy": spec.name,
                        "bar_frequency": bar_frequency,
                        "signal": _coerce_signal_value(engine.generate_signal(frame)),
                        "score": None,
                        "meta": None,
                    }
                )

        cross_specs = [item for item in strategy_specs if item.mode == "cross"]
        for spec in cross_specs:
            engine = spec.engine
            if not isinstance(engine, CrossSectionalStrategy):
                continue
            target_symbols = [symbol for symbol in selected_etfs if symbol in data_by_symbol] if spec.universe == "etf" else list(data_by_symbol.keys())
            scoped = {symbol: data_by_symbol[symbol] for symbol in target_symbols if symbol in data_by_symbol and not data_by_symbol[symbol].empty}
            if not scoped:
                continue
            signals = engine.generate_signals(scoped)
            for symbol, signal in signals.items():
                records.append(
                    {
                        "ts": signal_ts,
                        "symbol": symbol,
                        "strategy": spec.name,
                        "bar_frequency": bar_frequency,
                        "signal": _coerce_signal_value(signal),
                        "score": _extract_numeric_score(engine, symbol),
                        "meta": None,
                    }
                )

        if save and records:
            upsert_intraday_signals(session, records)

    return pd.DataFrame(records)


def export_intraday_signals(signal_ts: datetime, bar_frequency: str = "5", output_dir: str | Path = "reports/intraday", config: PostgresConfig | None = None) -> Path:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    with session_scope(config) as session:
        frame = load_intraday_signals(session, signal_ts=signal_ts, bar_frequency=bar_frequency)
    frame = enrich_signal_frame_with_symbol_names(frame)
    output_path = folder / f"signals_{bar_frequency}m_{signal_ts.strftime('%Y%m%d_%H%M')}.csv"
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
