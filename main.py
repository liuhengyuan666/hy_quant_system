from __future__ import annotations

import argparse
import json
from pathlib import Path

def command_init_db() -> None:
    from data_storage.database import init_database

    init_database()
    print("database initialized")


def command_sync_data(start_date: str, end_date: str | None) -> None:
    from config.settings import load_universe_config
    from data_service.sync_market import sync_market_data

    universe = load_universe_config()
    result = sync_market_data(
        index_symbols=universe.index_symbols,
        etf_symbols=universe.etf_symbols,
        start_date=start_date,
        end_date=end_date,
    )
    print(json.dumps(result, ensure_ascii=False))


def command_calc_indicators() -> None:
    from config.settings import load_universe_config
    from data_storage.indicators import refresh_technical_indicators

    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    rows = refresh_technical_indicators(symbols=symbols)
    print(json.dumps({"rows": rows}, ensure_ascii=False))


def command_gen_signals_with_selection(strategies: str | None) -> None:
    from config.settings import load_universe_config
    from signal_service.signal_generator import generate_daily_signals

    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    strategy_names = _parse_strategy_names(strategies)
    signals = generate_daily_signals(
        symbols=symbols,
        etf_symbols=universe.etf_symbols,
        strategy_names=strategy_names,
        save=True,
    )
    print(signals.to_string(index=False) if not signals.empty else "no signals generated")


def command_list_strategies() -> None:
    from strategy_engine.library import list_strategy_names

    print("\n".join(list_strategy_names()))


def command_backtest(symbol: str, strategy: str, limit: int) -> None:
    from backtest_engine.backtest_runner import run_backtest
    from data_storage.database import session_scope
    from data_storage.repository import load_market_prices

    if strategy.lower() != "ma":
        raise ValueError("currently only strategy=ma is supported by backtest runner")

    with session_scope() as session:
        data = load_market_prices(session, symbol=symbol, limit=limit)

    if data.empty:
        raise ValueError(f"no market data found for symbol: {symbol}")

    output = run_backtest(
        data=data,
        report_dir=Path("reports"),
        report_name=f"{symbol}_backtest_report.html",
    )
    payload = {
        "metrics": output.get("metrics"),
        "report_path": output.get("report_path", ""),
    }
    print(json.dumps(payload, ensure_ascii=False))


def command_run_pipeline() -> None:
    from scheduler.jobs import run_daily_pipeline

    result = run_daily_pipeline()
    print(json.dumps(result, ensure_ascii=False))


def command_run_and_analyze() -> None:
    from scheduler.jobs import run_and_analyze_pipeline

    result = run_and_analyze_pipeline()
    print(json.dumps(result, ensure_ascii=False))


def command_run_eod(frequencies: str | None) -> None:
    from analysis.eod_resampler import normalize_bar_frequencies
    from scheduler.jobs import run_eod_pipeline

    bar_frequencies = tuple(normalize_bar_frequencies(_parse_frequency_names(frequencies)))
    result = run_eod_pipeline(bar_frequencies=bar_frequencies)
    print(json.dumps(result, ensure_ascii=False))


def command_run_eod_and_analyze(frequencies: str | None) -> None:
    from analysis.eod_resampler import normalize_bar_frequencies
    from scheduler.jobs import run_eod_and_analyze_pipeline

    bar_frequencies = tuple(normalize_bar_frequencies(_parse_frequency_names(frequencies)))
    result = run_eod_and_analyze_pipeline(bar_frequencies=bar_frequencies)
    print(json.dumps(result, ensure_ascii=False))


def command_run_intraday(iterations: int | None) -> None:
    from scheduler.intraday_runner import start_intraday_loop

    start_intraday_loop(iterations=iterations)


def command_run_intraday_once() -> None:
    from scheduler.intraday_runner import run_intraday_iteration

    result = run_intraday_iteration()
    print(json.dumps(result, ensure_ascii=False))


def command_export_signal_summary() -> None:
    from signal_service.summary_view import export_signal_summary, resolve_summary_artifact_paths

    output_path = export_signal_summary()
    artifact_paths = resolve_summary_artifact_paths(output_path)
    print(
        json.dumps(
            {
                "summary_path": str(output_path),
                "push_path": str(artifact_paths["push_candidates_path"]),
            },
            ensure_ascii=False,
        )
    )


def command_gen_eod_signals(strategies: str | None, frequencies: str | None) -> None:
    from analysis.eod_resampler import normalize_bar_frequencies
    from config.settings import load_universe_config
    from signal_service.eod_generator import generate_eod_signals

    universe = load_universe_config()
    symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    strategy_names = _parse_strategy_names(strategies)
    bar_frequencies = normalize_bar_frequencies(_parse_frequency_names(frequencies))
    signals = generate_eod_signals(
        symbols=symbols,
        etf_symbols=universe.etf_symbols,
        strategy_names=strategy_names,
        bar_frequencies=bar_frequencies,
        save=True,
    )
    print(signals.to_string(index=False) if not signals.empty else "no EOD signals generated")


def _parse_strategy_names(value: str | None) -> list[str] | None:
    if value is None:
        return None
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        return None
    return names


def _parse_frequency_names(value: str | None) -> list[str] | None:
    if value is None:
        return None
    names = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not names:
        return None
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quant System CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    sync_parser = sub.add_parser("sync-data")
    sync_parser.add_argument("--start-date", default="20050101")
    sync_parser.add_argument("--end-date", default=None)

    sub.add_parser("calc-indicators")
    gen_parser = sub.add_parser("gen-signals")
    gen_parser.add_argument("--strategies", default=None)
    eod_parser = sub.add_parser("gen-eod-signals")
    eod_parser.add_argument("--strategies", default=None)
    eod_parser.add_argument("--frequencies", default="D,W,M")
    sub.add_parser("list-strategies")
    sub.add_parser("run-pipeline")
    sub.add_parser("run-and-analyze")
    run_eod_parser = sub.add_parser("run-eod")
    run_eod_parser.add_argument("--frequencies", default="D,W,M")
    run_eod_analyze_parser = sub.add_parser("run-eod-analyze")
    run_eod_analyze_parser.add_argument("--frequencies", default="D,W,M")
    intraday_parser = sub.add_parser("run-intraday")
    intraday_parser.add_argument("--iterations", type=int, default=None)
    sub.add_parser("run-intraday-once")
    sub.add_parser("export-signal-summary")
    sub.add_parser("run-scheduler")

    backtest_parser = sub.add_parser("backtest")
    backtest_parser.add_argument("--symbol", required=True)
    backtest_parser.add_argument("--strategy", default="ma")
    backtest_parser.add_argument("--limit", type=int, default=1200)

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "init-db":
        command_init_db()
    elif args.command == "sync-data":
        command_sync_data(start_date=args.start_date, end_date=args.end_date)
    elif args.command == "calc-indicators":
        command_calc_indicators()
    elif args.command == "gen-signals":
        command_gen_signals_with_selection(strategies=args.strategies)
    elif args.command == "gen-eod-signals":
        command_gen_eod_signals(strategies=args.strategies, frequencies=args.frequencies)
    elif args.command == "list-strategies":
        command_list_strategies()
    elif args.command == "backtest":
        command_backtest(symbol=args.symbol, strategy=args.strategy, limit=args.limit)
    elif args.command == "run-pipeline":
        command_run_pipeline()
    elif args.command == "run-and-analyze":
        command_run_and_analyze()
    elif args.command == "run-eod":
        command_run_eod(frequencies=args.frequencies)
    elif args.command == "run-eod-analyze":
        command_run_eod_and_analyze(frequencies=args.frequencies)
    elif args.command == "run-intraday":
        command_run_intraday(iterations=args.iterations)
    elif args.command == "run-intraday-once":
        command_run_intraday_once()
    elif args.command == "export-signal-summary":
        command_export_signal_summary()
    elif args.command == "run-scheduler":
        from scheduler.run_daily import start_scheduler

        start_scheduler()
    else:
        raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
