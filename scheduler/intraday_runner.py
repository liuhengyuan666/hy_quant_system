from __future__ import annotations

import json
import time
from datetime import date, datetime

import pandas as pd

from config.settings import load_runtime_config, load_universe_config
from core.clock import now_shanghai
from core.trading_calendar import is_preclose_window, is_trading_session
from data_service.realtime_etf import fetch_intraday_etf_bars
from data_service.realtime_index import fetch_intraday_index_bars
from data_storage.database import init_database, session_scope
from data_storage.realtime_repository import upsert_realtime_bars
from scheduler.jobs import run_preclose_analysis_pipeline
from signal_service.intraday_generator import export_intraday_signals, generate_intraday_signals
from signal_service.summary_view import export_signal_summary, resolve_summary_artifact_paths


def run_intraday_iteration(signal_ts: datetime | None = None) -> dict[str, object]:
    runtime = load_runtime_config()
    universe = load_universe_config()
    as_of = signal_ts or now_shanghai()
    bar_frequency = runtime.intraday_bar_frequency
    all_symbols = sorted(set(universe.index_symbols + universe.etf_symbols))

    frames: list[pd.DataFrame] = []
    for symbol in universe.index_symbols:
        try:
            frames.append(fetch_intraday_index_bars(symbol, period=bar_frequency))
        except Exception:
            continue
    for symbol in universe.etf_symbols:
        try:
            frames.append(fetch_intraday_etf_bars(symbol, period=bar_frequency))
        except Exception:
            continue

    merged = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"])
    init_database()
    bar_records: list[dict[str, object]] = []
    if not merged.empty:
        for record in merged.to_dict("records"):
            bar_records.append({str(key): value for key, value in record.items()})
    with session_scope() as session:
        bar_rows = upsert_realtime_bars(session, bar_records)

    signals = generate_intraday_signals(
        signal_ts=as_of,
        symbols=all_symbols,
        etf_symbols=universe.etf_symbols,
        bar_frequency=bar_frequency,
        lookback=runtime.intraday_lookback_bars,
        save=True,
    )
    export_path = export_intraday_signals(signal_ts=as_of, bar_frequency=bar_frequency)
    summary_path = export_signal_summary(intraday_ts=as_of, intraday_bar_frequency=bar_frequency)
    artifact_paths = resolve_summary_artifact_paths(summary_path)
    return {
        "ts": as_of.isoformat(),
        "bar_frequency": bar_frequency,
        "bar_rows": int(bar_rows),
        "signal_rows": int(len(signals.index)),
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "push_path": str(artifact_paths["push_candidates_path"]),
    }


def _should_trigger_preclose(
    current: datetime,
    runtime,
    last_triggered_date: date | None,
) -> bool:
    return is_preclose_window(current, runtime_config=runtime) and last_triggered_date != current.date()


def start_intraday_loop(iterations: int | None = None) -> None:
    runtime = load_runtime_config()
    if not runtime.intraday_enabled:
        raise RuntimeError("intraday mode disabled by runtime config")

    remaining = iterations
    last_preclose_trigger_date: date | None = None
    while remaining is None or remaining > 0:
        current = now_shanghai()
        if is_trading_session(current, runtime_config=runtime):
            payload = run_intraday_iteration(signal_ts=current)
            if _should_trigger_preclose(current, runtime=runtime, last_triggered_date=last_preclose_trigger_date):
                preclose_result = run_preclose_analysis_pipeline(signal_ts=current, use_intraday_snapshot=True)
                payload["preclose_triggered"] = True
                payload["preclose_path"] = str(preclose_result["csv_path"])
                payload["preclose_json_path"] = str(preclose_result["json_path"])
                last_preclose_trigger_date = current.date()
            else:
                payload["preclose_triggered"] = False
                payload["preclose_path"] = None
                payload["preclose_json_path"] = None
            print(json.dumps(payload, ensure_ascii=False))
            if remaining is not None:
                remaining -= 1
        time.sleep(runtime.intraday_interval_minutes * 60)
