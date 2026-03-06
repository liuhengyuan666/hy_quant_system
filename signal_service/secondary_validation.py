from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from config.settings import PostgresConfig


def _safe_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        converted = float(value)
    except ValueError:
        return None
    if pd.isna(converted):
        return None
    return float(converted)


def _safe_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, (str, int, float, date, datetime, pd.Timestamp)):
        return None
    try:
        converted = pd.Timestamp(value)
    except ValueError:
        return None
    if pd.isna(converted):
        return None
    return converted.date()


def _safe_int(value: object, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _normalize_signal(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"BUY", "SELL", "HOLD"}:
        return text
    return "HOLD"


def _market_metrics(frame: pd.DataFrame) -> dict[str, object]:
    default = {
        "close": None,
        "return_1d": None,
        "return_5d": None,
        "momentum_20": None,
        "ma20": None,
        "ma60": None,
        "volume_ratio": None,
        "price_accel_3": None,
        "trend_up": None,
        "trend_down": None,
        "first_negative_not_top": False,
        "blowoff_top": False,
    }
    if frame.empty:
        return default

    table = frame.sort_values("date").copy()
    for column in ["open", "high", "low", "close", "volume"]:
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce")

    required = ["close", "volume"]
    if any(column not in table.columns for column in required):
        return default

    table = table.dropna(subset=required)
    if len(table.index) < 2:
        return default

    close = table["close"].astype(float)
    volume = table["volume"].astype(float)

    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    return_1d = ((latest_close / prev_close) - 1.0) if prev_close != 0 else None

    return_5d: float | None = None
    if len(close.index) >= 6:
        ref = float(close.iloc[-6])
        if ref != 0:
            return_5d = (latest_close / ref) - 1.0

    momentum_20: float | None = None
    if len(close.index) >= 21:
        ref20 = float(close.iloc[-21])
        if ref20 != 0:
            momentum_20 = (latest_close / ref20) - 1.0

    ma20_series = close.rolling(20).mean()
    ma60_series = close.rolling(60).mean()
    ma20 = _safe_float(ma20_series.iloc[-1])
    ma60 = _safe_float(ma60_series.iloc[-1])

    trend_up: bool | None = None
    trend_down: bool | None = None
    if ma20 is not None and ma60 is not None:
        trend_up = latest_close > ma20 > ma60
        trend_down = latest_close < ma20 < ma60

    volume_ratio: float | None = None
    if len(volume.index) >= 3:
        baseline = volume.iloc[-21:-1].mean() if len(volume.index) >= 21 else volume.iloc[:-1].mean()
        baseline_value = _safe_float(baseline)
        if baseline_value is not None and baseline_value > 0:
            volume_ratio = float(volume.iloc[-1] / baseline_value)

    price_accel_3: float | None = None
    if len(close.index) >= 4:
        ref3 = float(close.iloc[-4])
        if ref3 != 0:
            price_accel_3 = (latest_close / ref3) - 1.0

    first_negative_not_top = False
    blowoff_top = False
    if return_1d is not None and len(close.index) >= 8:
        prev5_up = int(close.pct_change().tail(6).gt(0).sum())
        prior_uptrend = prev5_up >= 4 and float(close.iloc[-2]) > float(close.iloc[-7])
        first_negative = prior_uptrend and return_1d < 0
        if first_negative:
            if volume_ratio is not None and volume_ratio >= 2.0:
                blowoff_top = True
            else:
                first_negative_not_top = True

    return {
        "close": latest_close,
        "return_1d": return_1d,
        "return_5d": return_5d,
        "momentum_20": momentum_20,
        "ma20": ma20,
        "ma60": ma60,
        "volume_ratio": volume_ratio,
        "price_accel_3": price_accel_3,
        "trend_up": trend_up,
        "trend_down": trend_down,
        "first_negative_not_top": first_negative_not_top,
        "blowoff_top": blowoff_top,
    }


def _signal_summary(table: pd.DataFrame) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    grouped = table.groupby("symbol", dropna=False)

    for symbol, subset in grouped:
        counts = subset["signal"].value_counts(dropna=False)
        buy = int(counts.get("BUY", 0))
        sell = int(counts.get("SELL", 0))
        hold = int(counts.get("HOLD", 0))
        total = int(len(subset.index))

        if buy > sell and buy >= hold:
            primary = "BUY"
        elif sell > buy and sell >= hold:
            primary = "SELL"
        else:
            primary = "HOLD"

        divergence = 0.0
        if buy > 0 and sell > 0:
            divergence = float(min(buy, sell) / max(buy, sell))

        summary[str(symbol)] = {
            "buy": buy,
            "sell": sell,
            "hold": hold,
            "total": total,
            "net": buy - sell,
            "primary": primary,
            "divergence": divergence,
        }

    return summary


def _build_rule_result(
    rule_id: str,
    rule_text: str,
    status: str,
    summary: str,
    symbols: list[str],
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "rule_text": rule_text,
        "status": status,
        "summary": summary,
        "symbols": sorted(symbols),
    }


def build_secondary_validation(
    signals_frame: pd.DataFrame,
    market_data_by_symbol: dict[str, pd.DataFrame],
    signal_date: date,
) -> dict[str, object]:
    if signals_frame.empty:
        return {
            "signal_date": str(signal_date),
            "review_score": 50,
            "review_gate": "INSUFFICIENT_DATA",
            "rule_evaluations": [],
            "leader_symbols": [],
            "symbol_reviews": [],
        }

    table = signals_frame.copy()
    if "symbol" not in table.columns or "signal" not in table.columns:
        raise ValueError("signals frame must include symbol and signal columns")

    table["symbol"] = table["symbol"].astype(str)
    table["signal"] = table["signal"].map(_normalize_signal)
    if "name" in table.columns:
        table["name"] = table["name"].astype(str)
    else:
        table["name"] = table["symbol"]

    names = table.drop_duplicates(subset=["symbol"])[["symbol", "name"]]
    name_map = {str(row["symbol"]): str(row["name"]) for _, row in names.iterrows()}

    signal_summary = _signal_summary(table)
    symbol_metrics = {symbol: _market_metrics(frame) for symbol, frame in market_data_by_symbol.items()}

    momentum_rank_source: list[tuple[str, float]] = []
    for symbol, metrics in symbol_metrics.items():
        momentum = metrics.get("momentum_20")
        if isinstance(momentum, float):
            momentum_rank_source.append((symbol, momentum))
    momentum_rank_source.sort(key=lambda item: item[1], reverse=True)

    leader_count = max(1, int(len(momentum_rank_source) * 0.3)) if momentum_rank_source else 0
    leader_symbols = [item[0] for item in momentum_rank_source[:leader_count]]
    leader_set = set(leader_symbols)

    symbol_reviews: list[dict[str, object]] = []

    shrink_accel_sell_symbols: list[str] = []
    explosive_divergence_buy_symbols: list[str] = []
    contrarian_buy_symbols: list[str] = []
    crowded_sell_symbols: list[str] = []
    blowoff_top_symbols: list[str] = []
    first_negative_not_top_symbols: list[str] = []
    trend_conflict_symbols: list[str] = []
    leader_compliant_buys: list[str] = []
    exit_focus_symbols: list[str] = []

    for symbol, summary in signal_summary.items():
        metrics = symbol_metrics.get(symbol, _market_metrics(pd.DataFrame()))
        primary = str(summary["primary"])
        divergence = _safe_float(summary.get("divergence")) or 0.0
        trend_up = metrics.get("trend_up") is True
        trend_down = metrics.get("trend_down") is True
        momentum_20 = metrics.get("momentum_20")
        volume_ratio = metrics.get("volume_ratio")
        price_accel_3 = metrics.get("price_accel_3")

        shrink_accel_sell = (
            isinstance(price_accel_3, float)
            and isinstance(volume_ratio, float)
            and price_accel_3 > 0.03
            and volume_ratio < 0.85
        )
        explosive_divergence_buy = (
            isinstance(volume_ratio, float)
            and volume_ratio > 1.8
            and divergence >= 0.35
        )

        if shrink_accel_sell:
            shrink_accel_sell_symbols.append(symbol)
        if explosive_divergence_buy:
            explosive_divergence_buy_symbols.append(symbol)

        if (
            primary == "BUY"
            and isinstance(momentum_20, float)
            and momentum_20 < 0
            and isinstance(volume_ratio, float)
            and volume_ratio < 0.9
        ):
            contrarian_buy_symbols.append(symbol)

        if (
            primary == "SELL"
            and isinstance(momentum_20, float)
            and momentum_20 > 0.10
            and isinstance(volume_ratio, float)
            and volume_ratio > 1.3
        ):
            crowded_sell_symbols.append(symbol)

        blowoff_top = metrics.get("blowoff_top") is True
        first_negative_not_top = metrics.get("first_negative_not_top") is True
        if blowoff_top:
            blowoff_top_symbols.append(symbol)
        if first_negative_not_top:
            first_negative_not_top_symbols.append(symbol)

        if primary == "BUY" and symbol in leader_set and trend_up:
            leader_compliant_buys.append(symbol)

        if (primary == "BUY" and trend_down) or (primary == "SELL" and trend_up):
            trend_conflict_symbols.append(symbol)

        if primary == "SELL" or blowoff_top or (trend_down and metrics.get("return_1d") is not None):
            exit_focus_symbols.append(symbol)

        market_selection_ok = (
            (primary == "BUY" and trend_up)
            or (primary == "SELL" and trend_down)
            or primary == "HOLD"
        )

        if blowoff_top or (primary == "SELL" and trend_down):
            secondary_action = "SELL_CONFIRM"
        elif explosive_divergence_buy or (primary == "BUY" and symbol in leader_set and trend_up):
            secondary_action = "BUY_CONFIRM"
        elif primary == "BUY" and not trend_up:
            secondary_action = "BUY_FILTERED"
        else:
            secondary_action = "HOLD_OBSERVE"

        confidence = 50
        if secondary_action in {"BUY_CONFIRM", "SELL_CONFIRM"}:
            confidence += 15
        if market_selection_ok:
            confidence += 10
        if primary == "BUY" and symbol in leader_set:
            confidence += 10
        if shrink_accel_sell and primary == "BUY":
            confidence -= 12
        if primary == "BUY" and trend_down:
            confidence -= 15
        if primary == "SELL" and trend_up:
            confidence -= 15
        confidence = max(0, min(100, confidence))

        symbol_reviews.append(
            {
                "symbol": symbol,
                "name": name_map.get(symbol, symbol),
                "primary_action": primary,
                "secondary_action": secondary_action,
                "confidence": confidence,
                "signal_counts": {
                    "BUY": _safe_int(summary.get("buy")),
                    "SELL": _safe_int(summary.get("sell")),
                    "HOLD": _safe_int(summary.get("hold")),
                },
                "market_metrics": {
                    "return_1d": metrics.get("return_1d"),
                    "return_5d": metrics.get("return_5d"),
                    "momentum_20": metrics.get("momentum_20"),
                    "volume_ratio": metrics.get("volume_ratio"),
                    "trend_up": metrics.get("trend_up"),
                    "trend_down": metrics.get("trend_down"),
                },
                "checks": {
                    "shrink_accel_sell": shrink_accel_sell,
                    "explosive_divergence_buy": explosive_divergence_buy,
                    "first_negative_not_top": first_negative_not_top,
                    "blowoff_top": blowoff_top,
                    "market_selection_ok": market_selection_ok,
                },
            }
        )

    buy_symbols = [symbol for symbol, summary in signal_summary.items() if str(summary["primary"]) == "BUY"]
    sell_symbols = [symbol for symbol, summary in signal_summary.items() if str(summary["primary"]) == "SELL"]

    rule_evaluations = [
        _build_rule_result(
            "R1",
            "买在无人问津时，卖在人声鼎沸处",
            "PASS" if contrarian_buy_symbols or crowded_sell_symbols else "INFO",
            f"低关注逆向买点 {len(contrarian_buy_symbols)} 个，高拥挤卖点 {len(crowded_sell_symbols)} 个",
            contrarian_buy_symbols + crowded_sell_symbols,
        ),
        _build_rule_result(
            "R2",
            "缩量加速是卖点，爆量分歧是买点",
            "PASS" if shrink_accel_sell_symbols or explosive_divergence_buy_symbols else "INFO",
            f"缩量加速卖点 {len(shrink_accel_sell_symbols)} 个，爆量分歧买点 {len(explosive_divergence_buy_symbols)} 个",
            shrink_accel_sell_symbols + explosive_divergence_buy_symbols,
        ),
        _build_rule_result(
            "R3",
            "只做龙头，只做主升，只做惯性",
            "PASS" if (not buy_symbols or len(leader_compliant_buys) >= max(1, int(len(buy_symbols) * 0.6))) else "WARN",
            f"买入候选 {len(buy_symbols)} 个，其中龙头主升合规 {len(leader_compliant_buys)} 个",
            leader_compliant_buys,
        ),
        _build_rule_result(
            "R4",
            "龙头首阴不是顶，爆量换手才是顶",
            "WARN" if blowoff_top_symbols else "PASS",
            f"首阴非顶 {len(first_negative_not_top_symbols)} 个，爆量见顶预警 {len(blowoff_top_symbols)} 个",
            first_negative_not_top_symbols + blowoff_top_symbols,
        ),
        _build_rule_result(
            "R5",
            "龙是走出来的，不是猜出来的，要尊重市场选择",
            "PASS" if not trend_conflict_symbols else "WARN",
            f"顺市场候选 {len(signal_summary) - len(trend_conflict_symbols)} 个，逆市场冲突 {len(trend_conflict_symbols)} 个",
            trend_conflict_symbols,
        ),
        _build_rule_result(
            "R6",
            "会买是徒弟，会卖才是师傅",
            "PASS" if exit_focus_symbols else "INFO",
            f"出现卖出/退出关注标的 {len(exit_focus_symbols)} 个（主卖出 {len(sell_symbols)} 个）",
            exit_focus_symbols,
        ),
        _build_rule_result(
            "R7",
            "顺势而为，趋势不对努力白费",
            "PASS" if not trend_conflict_symbols else "WARN",
            f"趋势一致 {len(signal_summary) - len(trend_conflict_symbols)} 个，趋势冲突 {len(trend_conflict_symbols)} 个",
            trend_conflict_symbols,
        ),
    ]

    pass_count = sum(1 for item in rule_evaluations if item["status"] == "PASS")
    warn_count = sum(1 for item in rule_evaluations if item["status"] == "WARN")

    review_score = max(0, min(100, 70 + (pass_count * 5) - (warn_count * 10)))
    if warn_count >= 3:
        review_gate = "REJECT"
    elif warn_count >= 1:
        review_gate = "CAUTION"
    else:
        review_gate = "CONFIRM"

    symbol_reviews.sort(key=lambda item: (str(item["symbol"])))
    return {
        "signal_date": str(signal_date),
        "review_score": review_score,
        "review_gate": review_gate,
        "leader_symbols": leader_symbols,
        "rule_evaluations": rule_evaluations,
        "symbol_reviews": symbol_reviews,
    }


def secondary_validate_signals_csv(
    csv_path: str | Path,
    lookback: int = 240,
    config: PostgresConfig | None = None,
) -> dict[str, object]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"signals file not found: {path}")

    frame = pd.read_csv(
        path,
        dtype={
            "date": "string",
            "symbol": "string",
            "name": "string",
            "strategy": "string",
            "signal": "string",
        },
    )
    if frame.empty:
        fallback_date = date.today()
        return build_secondary_validation(frame, market_data_by_symbol={}, signal_date=fallback_date)

    signal_date = _safe_date(frame["date"].iloc[0])
    if signal_date is None:
        signal_date = date.today()

    symbols = sorted(frame["symbol"].astype(str).unique().tolist())

    from data_storage.database import session_scope
    from data_storage.repository import load_market_prices_map

    with session_scope(config) as session:
        market_data_by_symbol = load_market_prices_map(
            session,
            symbols,
            limit=max(lookback, 80),
            as_of_date=signal_date,
        )

    return build_secondary_validation(
        signals_frame=frame,
        market_data_by_symbol=market_data_by_symbol,
        signal_date=signal_date,
    )
