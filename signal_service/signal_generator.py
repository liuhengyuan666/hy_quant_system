from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd

from config.settings import PostgresConfig
from signal_service.eod_generator import export_eod_signals, generate_eod_signals
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names


def generate_daily_signals(
    symbols: Sequence[str] | None = None,
    etf_symbols: Sequence[str] | None = None,
    strategy_names: Sequence[str] | None = None,
    as_of_date: date | None = None,
    lookback: int = 900,
    save: bool = True,
    config: PostgresConfig | None = None,
) -> pd.DataFrame:
    frame = generate_eod_signals(
        symbols=symbols,
        etf_symbols=etf_symbols,
        strategy_names=strategy_names,
        as_of_date=as_of_date,
        lookback=lookback,
        bar_frequencies=("D",),
        save=save,
        config=config,
    )
    if frame.empty:
        return frame
    return frame[frame["bar_frequency"] == "D"].reset_index(drop=True)


def export_daily_signals(
    signal_date: date | None = None,
    output_dir: str | Path = "reports",
    config: PostgresConfig | None = None,
) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    source_paths = export_eod_signals(signal_date=signal_date, bar_frequencies=("D",), output_dir=target_dir, config=config)
    if not source_paths:
        output_path = target_dir / f"signals_{(signal_date or date.today()).strftime('%Y%m%d')}.csv"
        pd.DataFrame(columns=["date", "symbol", "strategy", "signal", "score", "meta"]).to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )
        return output_path

    source_path = source_paths[0]
    target_path = target_dir / f"signals_{source_path.stem.split('_')[-1]}.csv"
    frame = pd.read_csv(source_path, dtype={"symbol": "string", "strategy": "string", "signal": "string"})
    frame = enrich_signal_frame_with_symbol_names(frame)
    frame.to_csv(target_path, index=False, encoding="utf-8-sig")
    return target_path
