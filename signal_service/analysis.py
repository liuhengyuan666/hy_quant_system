from __future__ import annotations

from pathlib import Path

import pandas as pd


def _normalize_signal(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"BUY", "SELL", "HOLD"}:
        return text
    return "HOLD"


def _counts_by_value(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts(dropna=False)
    return {
        "BUY": int(counts.get("BUY", 0)),
        "SELL": int(counts.get("SELL", 0)),
        "HOLD": int(counts.get("HOLD", 0)),
    }


def _dominant_action(buy: int, sell: int, hold: int) -> str:
    options = [("BUY", buy), ("SELL", sell), ("HOLD", hold)]
    options.sort(key=lambda item: item[1], reverse=True)
    if len(options) > 1 and options[0][1] == options[1][1]:
        return "MIXED"
    return options[0][0]


def _summarize_group(frame: pd.DataFrame, group_col: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    grouped = frame.groupby(group_col, dropna=False)

    for group_value, subset in grouped:
        counts = _counts_by_value(subset["signal"])
        buy = counts["BUY"]
        sell = counts["SELL"]
        hold = counts["HOLD"]

        rows.append(
            {
                group_col: str(group_value),
                "BUY": buy,
                "SELL": sell,
                "HOLD": hold,
                "total": int(len(subset.index)),
                "net_bias": int(buy - sell),
                "dominant_action": _dominant_action(buy=buy, sell=sell, hold=hold),
            }
        )

    rows.sort(key=lambda item: item[group_col])
    return rows


def analyze_signals_dataframe(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {
            "date": None,
            "total_signals": 0,
            "signal_counts": {"BUY": 0, "SELL": 0, "HOLD": 0},
            "strategy_summary": [],
            "symbol_summary": [],
            "top_buy_symbols": [],
            "top_sell_symbols": [],
        }

    table = frame.copy()
    required = ["date", "symbol", "strategy", "signal"]
    for column in required:
        if column not in table.columns:
            raise ValueError(f"missing required column: {column}")

    table["date"] = table["date"].astype(str)
    table["symbol"] = table["symbol"].astype(str)
    table["strategy"] = table["strategy"].astype(str)
    table["signal"] = table["signal"].map(_normalize_signal)

    signal_counts = _counts_by_value(table["signal"])
    strategy_summary = _summarize_group(table, "strategy")
    symbol_summary = _summarize_group(table, "symbol")

    sorted_buy = sorted(symbol_summary, key=lambda item: (-item["BUY"], item["symbol"]))
    sorted_sell = sorted(symbol_summary, key=lambda item: (-item["SELL"], item["symbol"]))

    return {
        "date": table["date"].iloc[0],
        "total_signals": int(len(table.index)),
        "signal_counts": signal_counts,
        "strategy_summary": strategy_summary,
        "symbol_summary": symbol_summary,
        "top_buy_symbols": [item["symbol"] for item in sorted_buy[:3] if item["BUY"] > 0],
        "top_sell_symbols": [item["symbol"] for item in sorted_sell[:3] if item["SELL"] > 0],
    }


def analyze_signals_csv(csv_path: str | Path) -> dict[str, object]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"signals file not found: {path}")

    frame = pd.read_csv(
        path,
        dtype={
            "date": "string",
            "symbol": "string",
            "strategy": "string",
            "signal": "string",
        },
    )
    result = analyze_signals_dataframe(frame)
    result["source_file"] = str(path)
    return result
