from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtest_engine.report import generate_html_report
from backtest_engine.strategy_adapter import MovingAverageCrossStrategy, bt


def _prepare_bt_data(data: pd.DataFrame) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"missing columns for backtest: {missing}")

    frame = data.copy()
    frame["datetime"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["datetime"]).sort_values("datetime")
    frame = frame.set_index("datetime")
    frame = frame[["open", "high", "low", "close", "volume"]]
    frame = frame.apply(pd.to_numeric, errors="coerce").dropna()
    return frame


def _extract_metrics(strategy_result) -> dict[str, float]:
    returns = strategy_result.analyzers.returns.get_analysis()
    drawdown = strategy_result.analyzers.drawdown.get_analysis()
    sharpe = strategy_result.analyzers.sharpe.get_analysis()
    trades = strategy_result.analyzers.trades.get_analysis()

    annual_return = float(returns.get("rnorm100", 0.0) or 0.0)
    max_drawdown = float(drawdown.get("max", {}).get("drawdown", 0.0) or 0.0)
    sharpe_ratio = float(sharpe.get("sharperatio", 0.0) or 0.0)

    closed_count = int(trades.get("total", {}).get("closed", 0) or 0)
    win_count = int(trades.get("won", {}).get("total", 0) or 0)
    win_rate = float(win_count / closed_count) if closed_count > 0 else 0.0

    return {
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "win_rate": win_rate,
        "trade_count": float(closed_count),
    }


def _build_equity_curve(time_return: dict, starting_cash: float) -> pd.DataFrame:
    if not time_return:
        return pd.DataFrame(columns=["date", "equity"])

    rows: list[dict[str, object]] = []
    equity = float(starting_cash)
    for key in sorted(time_return.keys()):
        daily_return = float(time_return[key])
        equity *= 1 + daily_return
        rows.append({"date": pd.to_datetime(key).date(), "equity": equity})
    return pd.DataFrame(rows)


def run_backtest(
    data: pd.DataFrame,
    strategy_cls=None,
    starting_cash: float = 1_000_000,
    commission: float = 0.001,
    report_dir: str | Path | None = None,
    report_name: str | None = None,
) -> dict[str, object]:
    if bt is None:
        raise ImportError("backtrader is required for backtesting")

    strategy = strategy_cls or MovingAverageCrossStrategy
    bt_data = _prepare_bt_data(data)
    if bt_data.empty:
        raise ValueError("no valid data available for backtesting")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(float(starting_cash))
    cerebro.broker.setcommission(commission=float(commission))

    feed = bt.feeds.PandasData(dataname=bt_data)
    cerebro.adddata(feed)
    cerebro.addstrategy(strategy)

    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", annualize=True)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")

    result = cerebro.run(maxcpus=1)[0]
    metrics = _extract_metrics(result)
    equity_curve = _build_equity_curve(result.analyzers.time_return.get_analysis(), starting_cash=float(starting_cash))

    output: dict[str, object] = {"metrics": metrics, "equity_curve": equity_curve}

    if report_dir is not None:
        folder = Path(report_dir)
        symbol = str(data["symbol"].iloc[-1]) if "symbol" in data.columns and not data.empty else "unknown"
        filename = report_name or f"{symbol}_backtest_report.html"
        report_path = generate_html_report(metrics, equity_curve, folder / filename)
        output["report_path"] = str(report_path)

    return output
