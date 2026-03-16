from __future__ import annotations

from pathlib import Path

from analysis.eod_resampler import normalize_bar_frequencies
from config.settings import load_universe_config
from data_service.sync_market import sync_market_data
from data_storage.indicators import refresh_technical_indicators
from signal_service.eod_generator import export_eod_signals, generate_eod_signals
from signal_service.data_gap_report import export_data_gap_report
from signal_service.daily_conclusion_report import export_daily_conclusion_report
from signal_service.preclose_decision import run_preclose_analysis
from signal_service.summary_view import export_signal_summary, resolve_summary_artifact_paths
from signal_service.analysis import analyze_signals_csv
from signal_service.strategy_matrix_report import export_strategy_matrix_report
from signal_service.secondary_validation import secondary_validate_signals_csv
from signal_service.signal_generator import export_daily_signals, generate_daily_signals


def update_market_job() -> dict[str, int]:
    universe = load_universe_config()
    return sync_market_data(
        index_symbols=universe.index_symbols,
        etf_symbols=universe.etf_symbols,
    )


def calc_indicators_job() -> int:
    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    return refresh_technical_indicators(symbols=symbols)


def generate_signals_job() -> int:
    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    signals = generate_daily_signals(symbols=symbols, etf_symbols=universe.etf_symbols, save=True)
    return int(len(signals.index))


def generate_eod_signals_job(bar_frequencies: tuple[str, ...] = ("D", "W", "M")) -> dict[str, int]:
    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    signals = generate_eod_signals(
        symbols=symbols,
        etf_symbols=universe.etf_symbols,
        bar_frequencies=bar_frequencies,
        save=True,
    )
    frequencies = normalize_bar_frequencies(bar_frequencies)
    if signals.empty:
        return {frequency: 0 for frequency in frequencies}
    counts = signals["bar_frequency"].value_counts().to_dict()
    return {frequency: int(counts.get(frequency, 0)) for frequency in frequencies}


def export_signals_job() -> str:
    output = export_daily_signals()
    return str(output)


def export_eod_signals_job(bar_frequencies: tuple[str, ...] = ("D", "W", "M")) -> list[str]:
    outputs = export_eod_signals(bar_frequencies=bar_frequencies)
    return [str(path) for path in outputs]


def run_daily_pipeline() -> dict[str, object]:
    market_result = update_market_job()
    indicator_rows = calc_indicators_job()
    signal_rows = generate_signals_job()
    export_path = export_signals_job()
    return {
        "market_rows": int(market_result.get("rows", 0)),
        "indicator_rows": int(indicator_rows),
        "signal_rows": int(signal_rows),
        "export_path": export_path,
    }


def run_eod_pipeline(bar_frequencies: tuple[str, ...] = ("D", "W", "M")) -> dict[str, object]:
    market_result = update_market_job()
    indicator_rows = calc_indicators_job()
    signal_counts = generate_eod_signals_job(bar_frequencies=bar_frequencies)
    export_paths = export_eod_signals_job(bar_frequencies=bar_frequencies)
    return {
        "market_rows": int(market_result.get("rows", 0)),
        "indicator_rows": int(indicator_rows),
        "signal_counts": signal_counts,
        "export_paths": export_paths,
    }


def run_and_analyze_pipeline() -> dict[str, object]:
    pipeline_result = run_daily_pipeline()
    export_path = str(pipeline_result.get("export_path", ""))
    analysis = analyze_signals_csv(export_path) if export_path else {}
    secondary_validation = secondary_validate_signals_csv(export_path) if export_path else {}
    return {
        **pipeline_result,
        "analysis": analysis,
        "secondary_validation": secondary_validation,
    }


def run_eod_and_analyze_pipeline(bar_frequencies: tuple[str, ...] = ("D", "W", "M")) -> dict[str, object]:
    pipeline_result = run_eod_pipeline(bar_frequencies=bar_frequencies)
    analyses: dict[str, object] = {}
    secondary_validations: dict[str, object] = {}
    export_paths = pipeline_result.get("export_paths", [])
    if not isinstance(export_paths, list):
        export_paths = []
    for export_path in export_paths:
        frequency = Path(str(export_path)).stem.split("_")[-2].upper()
        analyses[frequency] = analyze_signals_csv(export_path)
        secondary_validations[frequency] = secondary_validate_signals_csv(export_path)
    summary_path = export_signal_summary()
    artifact_paths = resolve_summary_artifact_paths(summary_path)
    preclose_result = run_preclose_analysis(use_intraday_snapshot=False)
    daily_conclusion_result = export_daily_conclusion_report()
    data_gap_result = export_data_gap_report()
    strategy_matrix_result = export_strategy_matrix_report()
    return {
        **pipeline_result,
        "analysis": analyses,
        "secondary_validation": secondary_validations,
        "summary_path": str(summary_path),
        "push_path": str(artifact_paths["push_candidates_path"]),
        "preclose_path": str(preclose_result["csv_path"]),
        "preclose_json_path": str(preclose_result["json_path"]),
        "daily_conclusion_path": str(daily_conclusion_result["csv_path"]),
        "daily_conclusion_operation_path": str(daily_conclusion_result["operation_csv_path"]),
        "daily_conclusion_json_path": str(daily_conclusion_result["json_path"]),
        "daily_conclusion_xlsx_path": str(daily_conclusion_result["xlsx_path"]),
        "data_gap_path": str(data_gap_result["csv_path"]),
        "data_gap_xlsx_path": str(data_gap_result["xlsx_path"]),
        "strategy_matrix_path": str(strategy_matrix_result["xlsx_path"]),
    }


def run_preclose_analysis_pipeline(signal_ts=None, signal_date=None, use_intraday_snapshot: bool = False) -> dict[str, object]:
    return run_preclose_analysis(signal_ts=signal_ts, signal_date=signal_date, use_intraday_snapshot=use_intraday_snapshot)


def export_strategy_matrix_report_pipeline(signal_date=None, intraday_ts=None) -> dict[str, object]:
    return export_strategy_matrix_report(signal_date=signal_date, intraday_ts=intraday_ts)


def export_daily_conclusion_report_pipeline(signal_date=None, intraday_ts=None) -> dict[str, object]:
    return export_daily_conclusion_report(signal_date=signal_date, intraday_ts=intraday_ts)


def export_data_gap_report_pipeline(signal_date=None, intraday_ts=None) -> dict[str, object]:
    return export_data_gap_report(signal_date=signal_date, intraday_ts=intraday_ts)
