from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from analysis.eod_resampler import normalize_bar_frequencies, resample_ohlcv
from config.settings import PostgresConfig, load_universe_config
from core.modes import AnalysisMode
from core.trading_calendar import latest_closed_trading_date
from data_storage.database import init_database, session_scope
from data_storage.repository import load_latest_market_date, load_market_prices_map, load_signals_by_date, upsert_signals
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names
from strategy_engine.base import CrossSectionalStrategy, Signal, Strategy
from strategy_engine.library import StrategySpec, resolve_strategy_specs


def _single_symbol_records(
    data_by_symbol: dict[str, pd.DataFrame],
    strategy_specs: list[StrategySpec],
    as_of: date,
    bar_frequency: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    single_specs = [item for item in strategy_specs if item.mode == "single"]

    for symbol, frame in data_by_symbol.items():
        if frame.empty:
            continue
        for spec in single_specs:
            engine = spec.engine
            if not isinstance(engine, Strategy):
                continue
            signal = engine.generate_signal(frame)
            records.append(
                {
                    "date": as_of,
                    "symbol": symbol,
                    "strategy": spec.name,
                    "signal": _coerce_signal_value(signal),
                    "score": None,
                    "meta": None,
                    "mode": AnalysisMode.EOD.value,
                    "bar_frequency": bar_frequency,
                }
            )

    return records


def _cross_symbol_records(
    data_by_symbol: dict[str, pd.DataFrame],
    etf_symbols: Sequence[str],
    strategy_specs: list[StrategySpec],
    as_of: date,
    bar_frequency: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    cross_specs = [item for item in strategy_specs if item.mode == "cross"]

    for spec in cross_specs:
        engine = spec.engine
        if not isinstance(engine, CrossSectionalStrategy):
            continue

        if spec.universe == "etf":
            target_symbols = [symbol for symbol in etf_symbols if symbol in data_by_symbol]
        else:
            target_symbols = list(data_by_symbol.keys())

        scoped_data = {symbol: data_by_symbol[symbol] for symbol in target_symbols if symbol in data_by_symbol}
        if not scoped_data:
            continue

        signals = engine.generate_signals(scoped_data)
        for symbol, signal in signals.items():
            records.append(
                {
                    "date": as_of,
                    "symbol": symbol,
                    "strategy": spec.name,
                    "signal": _coerce_signal_value(signal),
                    "score": _extract_numeric_score(engine, symbol),
                    "meta": None,
                    "mode": AnalysisMode.EOD.value,
                    "bar_frequency": bar_frequency,
                }
            )

    return records


def _extract_numeric_score(engine: CrossSectionalStrategy, symbol: str) -> float | None:
    for attribute in ["last_scores", "last_momentum"]:
        value = getattr(engine, attribute, None)
        if isinstance(value, dict):
            score = value.get(symbol)
            if isinstance(score, (float, int)):
                return float(score)
    return None


def _coerce_signal_value(value: object) -> str:
    if isinstance(value, Signal):
        return value.value
    return str(value)


def _resolve_as_of_date(
    config: PostgresConfig | None,
    selected_symbols: Sequence[str],
    explicit_date: date | None,
) -> date:
    if explicit_date is not None:
        return explicit_date

    with session_scope(config) as session:
        latest = load_latest_market_date(session, selected_symbols)
    return latest or latest_closed_trading_date()


def generate_eod_signals(
    symbols: Sequence[str] | None = None,
    etf_symbols: Sequence[str] | None = None,
    strategy_names: Sequence[str] | None = None,
    as_of_date: date | None = None,
    lookback: int = 900,
    bar_frequencies: Iterable[str] | None = None,
    save: bool = True,
    config: PostgresConfig | None = None,
) -> pd.DataFrame:
    universe = load_universe_config()
    selected_symbols = list(symbols or sorted(set(universe.index_symbols + universe.etf_symbols)))
    selected_etfs = list(etf_symbols or universe.etf_symbols)
    strategy_specs = resolve_strategy_specs(strategy_names, supported_mode="eod")
    frequencies = normalize_bar_frequencies(bar_frequencies)

    init_database(config)
    target_date = _resolve_as_of_date(config=config, selected_symbols=selected_symbols, explicit_date=as_of_date)
    with session_scope(config) as session:
        raw_data_by_symbol = load_market_prices_map(session, selected_symbols, limit=lookback, as_of_date=target_date)
        records: list[dict[str, object]] = []

        for frequency in frequencies:
            resampled = {
                symbol: resample_ohlcv(frame, frequency)
                for symbol, frame in raw_data_by_symbol.items()
            }
            records.extend(
                _single_symbol_records(
                    resampled,
                    strategy_specs=strategy_specs,
                    as_of=target_date,
                    bar_frequency=frequency,
                )
            )
            records.extend(
                _cross_symbol_records(
                    resampled,
                    etf_symbols=selected_etfs,
                    strategy_specs=strategy_specs,
                    as_of=target_date,
                    bar_frequency=frequency,
                )
            )

        if save and records:
            upsert_signals(session, records)

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    return frame.sort_values(["bar_frequency", "strategy", "symbol"]).reset_index(drop=True)


def export_eod_signals(
    signal_date: date | None = None,
    bar_frequencies: Iterable[str] | None = None,
    output_dir: str | Path = "reports/eod",
    config: PostgresConfig | None = None,
) -> list[Path]:
    target_date = signal_date or latest_closed_trading_date()
    frequencies = normalize_bar_frequencies(bar_frequencies)
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    output_paths: list[Path] = []
    with session_scope(config) as session:
        for frequency in frequencies:
            signals = load_signals_by_date(
                session,
                target_date,
                mode=AnalysisMode.EOD.value,
                bar_frequency=frequency,
            )
            signals = enrich_signal_frame_with_symbol_names(signals)
            output_path = folder / f"signals_{frequency.lower()}_{target_date.strftime('%Y%m%d')}.csv"
            signals.to_csv(output_path, index=False, encoding="utf-8-sig")
            output_paths.append(output_path)
    return output_paths
