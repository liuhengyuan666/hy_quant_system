from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from config.settings import PostgresConfig, load_runtime_config, load_universe_config
from core.trading_calendar import resolve_preclose_signal_date
from data_storage.database import session_scope
from data_storage.realtime_repository import load_intraday_signals, load_realtime_bars_map
from data_storage.repository import load_latest_signal_date_on_or_before, load_market_prices_map, load_signals_by_date
from signal_service.secondary_validation import build_secondary_validation
from signal_service.summary_view import build_signal_summary
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names

PrecloseMode = Literal["POST_CLOSE", "INTRADAY_PRE_CLOSE"]
SECTOR_KEYWORDS = {"银行", "券商", "有色", "通信", "电力"}
THEME_KEYWORDS = {"人工智能", "金融科技", "科技", "AH股", "科创"}

PRE_CLOSE_COLUMNS = [
    "analysis_mode",
    "analysis_ts",
    "signal_date",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "decision_signal",
    "decision_score",
    "decision_reason",
    "trend_state",
    "latest_price",
    "prev_close",
    "session_open",
    "session_high",
    "session_low",
    "day_change_pct",
    "pullback_from_high_pct",
    "rebound_from_low_pct",
    "distance_to_ma20_pct",
    "distance_to_ma60_pct",
    "eod_d",
    "eod_w",
    "eod_m",
    "intraday",
    "eod_bias",
    "alignment",
    "secondary_action",
    "secondary_confidence",
    "review_gate",
    "review_score",
    "composite_score",
    "dashboard_action",
    "conviction_rank",
]


def _safe_float(value: object) -> float | None:
    converted = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(converted):
        return None
    return float(converted)


def _empty_preclose_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=PRE_CLOSE_COLUMNS)


def _classify_asset_type(display_symbol: object) -> str:
    return "ETF" if str(display_symbol).startswith("E") else "INDEX"


def _classify_bucket(name: object, asset_type: object) -> str:
    title = str(name)
    kind = str(asset_type)
    if "恒生" in title or "AH股" in title or "港股" in title:
        return "港股"
    if any(keyword in title for keyword in SECTOR_KEYWORDS):
        return "行业"
    if any(keyword in title for keyword in THEME_KEYWORDS):
        return "主题"
    if kind == "ETF":
        return "宽基ETF"
    return "宽基指数"


def _fallback_summary_rows(symbols: list[str], start_rank: int = 1) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    rows = pd.DataFrame({"symbol": symbols})
    rows = enrich_signal_frame_with_symbol_names(rows)
    rows["asset_type"] = rows["display_symbol"].map(_classify_asset_type)
    rows["bucket"] = rows.apply(lambda row: _classify_bucket(row.get("name"), row.get("asset_type")), axis=1)
    rows["eod_d"] = "HOLD"
    rows["eod_w"] = "HOLD"
    rows["eod_m"] = "HOLD"
    rows["intraday"] = "HOLD"
    rows["eod_bias"] = "HOLD"
    rows["alignment"] = "NEUTRAL"
    rows["secondary_action"] = "HOLD_OBSERVE"
    rows["secondary_confidence"] = 50.0
    rows["review_gate"] = "INSUFFICIENT_DATA"
    rows["review_score"] = 50.0
    rows["composite_score"] = 0.0
    rows["dashboard_action"] = "NEUTRAL"
    rows["conviction_rank"] = pd.RangeIndex(start=start_rank, stop=start_rank + len(rows.index))
    return rows


def _ensure_preclose_summary_rows(summary: pd.DataFrame, fallback_symbols: list[str] | None = None) -> pd.DataFrame:
    defaults: dict[str, str | float] = {
        "eod_d": "HOLD",
        "eod_w": "HOLD",
        "eod_m": "HOLD",
        "intraday": "HOLD",
        "eod_bias": "HOLD",
        "alignment": "NEUTRAL",
        "secondary_action": "HOLD_OBSERVE",
        "secondary_confidence": 50.0,
        "review_gate": "INSUFFICIENT_DATA",
        "review_score": 50.0,
        "composite_score": 0.0,
        "dashboard_action": "NEUTRAL",
    }
    if summary.empty:
        return _fallback_summary_rows(sorted(set(fallback_symbols or [])), start_rank=1)

    table = summary.copy()
    missing_symbols = sorted(set(fallback_symbols or []) - set(table.get("symbol", pd.Series(dtype="string")).astype(str).tolist()))
    if missing_symbols:
        existing_ranks = pd.to_numeric(table.get("conviction_rank", pd.Series(dtype="float64")), errors="coerce")
        next_rank = int(existing_ranks.max()) + 1 if not existing_ranks.dropna().empty else 1
        table = pd.concat([table, _fallback_summary_rows(missing_symbols, start_rank=next_rank)], ignore_index=True)

    for column, default in defaults.items():
        if column not in table.columns:
            table[column] = default
        elif isinstance(default, str):
            table[column] = table[column].fillna(default)
        else:
            table[column] = pd.to_numeric(table[column], errors="coerce").fillna(float(default))
    if "conviction_rank" not in table.columns:
        table["conviction_rank"] = pd.RangeIndex(start=1, stop=len(table.index) + 1)
    table["symbol"] = table["symbol"].astype(str)
    return table.sort_values(["conviction_rank", "symbol"], ascending=[True, True]).reset_index(drop=True)


def _latest_bar_metrics(daily_frame: pd.DataFrame, intraday_frame: pd.DataFrame | None = None) -> dict[str, float | None]:
    if daily_frame.empty:
        return {
            "latest_price": None,
            "prev_close": None,
            "session_open": None,
            "session_high": None,
            "session_low": None,
            "ma20": None,
            "ma60": None,
        }

    ordered_daily = daily_frame.sort_values("date").copy()
    for column in ["open", "high", "low", "close", "volume"]:
        if column in ordered_daily.columns:
            ordered_daily[column] = pd.to_numeric(ordered_daily[column], errors="coerce")

    close = ordered_daily["close"].astype(float)
    latest_close = _safe_float(close.iloc[-1])
    prev_close = _safe_float(close.iloc[-2]) if len(close.index) >= 2 else None
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1]) if len(close.index) >= 20 else None
    ma60 = _safe_float(close.rolling(60).mean().iloc[-1]) if len(close.index) >= 60 else None

    if intraday_frame is None or intraday_frame.empty:
        latest_row = ordered_daily.iloc[-1]
        return {
            "latest_price": latest_close,
            "prev_close": prev_close,
            "session_open": _safe_float(latest_row.get("open")),
            "session_high": _safe_float(latest_row.get("high")),
            "session_low": _safe_float(latest_row.get("low")),
            "ma20": ma20,
            "ma60": ma60,
        }

    ordered_intraday = intraday_frame.sort_values("date").copy()
    for column in ["open", "high", "low", "close"]:
        if column in ordered_intraday.columns:
            ordered_intraday[column] = pd.to_numeric(ordered_intraday[column], errors="coerce")

    ordered_intraday = ordered_intraday.dropna(subset=["open", "high", "low", "close"])
    if ordered_intraday.empty:
        latest_row = ordered_daily.iloc[-1]
        return {
            "latest_price": latest_close,
            "prev_close": prev_close,
            "session_open": _safe_float(latest_row.get("open")),
            "session_high": _safe_float(latest_row.get("high")),
            "session_low": _safe_float(latest_row.get("low")),
            "ma20": ma20,
            "ma60": ma60,
        }

    return {
        "latest_price": _safe_float(ordered_intraday.iloc[-1].get("close")),
        "prev_close": prev_close,
        "session_open": _safe_float(ordered_intraday.iloc[0].get("open")),
        "session_high": _safe_float(ordered_intraday["high"].max()),
        "session_low": _safe_float(ordered_intraday["low"].min()),
        "ma20": ma20,
        "ma60": ma60,
    }


def _pct_delta(current: float | None, reference: float | None) -> float | None:
    if current is None or reference is None or reference == 0:
        return None
    return float((current / reference) - 1.0)


def _trend_state(latest_price: float | None, ma20: float | None, ma60: float | None) -> str:
    if latest_price is None:
        return "NEUTRAL"
    if ma20 is not None and ma60 is not None:
        if latest_price > ma20 > ma60:
            return "UPTREND"
        if latest_price < ma20 < ma60:
            return "DOWNTREND"
        return "NEUTRAL"
    if ma20 is not None and latest_price > ma20:
        return "UPTREND"
    if ma20 is not None and latest_price < ma20:
        return "DOWNTREND"
    if ma60 is not None and latest_price > ma60:
        return "UPTREND"
    if ma60 is not None and latest_price < ma60:
        return "DOWNTREND"
    return "NEUTRAL"


def _score_preclose_decision(row: pd.Series) -> tuple[float, list[str]]:
    base_score = _safe_float(row.get("composite_score"))
    score = 0.0 if base_score is None else base_score
    reasons: list[str] = []
    eod_bias = str(row.get("eod_bias", "HOLD"))
    trend_state = str(row.get("trend_state", "NEUTRAL"))
    review_gate = str(row.get("review_gate", "INSUFFICIENT_DATA"))
    day_change_pct = _safe_float(row.get("day_change_pct"))
    pullback_from_high_pct = _safe_float(row.get("pullback_from_high_pct"))
    rebound_from_low_pct = _safe_float(row.get("rebound_from_low_pct"))
    distance_to_ma20_pct = _safe_float(row.get("distance_to_ma20_pct"))

    if eod_bias == "BUY" and trend_state == "UPTREND":
        score += 0.8
        reasons.append("trend_supports_buy")
    if eod_bias == "SELL" and trend_state == "DOWNTREND":
        score -= 0.8
        reasons.append("trend_supports_sell")

    if eod_bias == "BUY" and distance_to_ma20_pct is not None and -0.02 <= distance_to_ma20_pct <= 0.03:
        score += 0.8
        reasons.append("price_near_ma20")
    if eod_bias == "SELL" and distance_to_ma20_pct is not None and distance_to_ma20_pct <= -0.01:
        score -= 0.6
        reasons.append("price_below_ma20")

    if eod_bias == "BUY" and pullback_from_high_pct is not None and -0.025 <= pullback_from_high_pct <= -0.003:
        score += 0.6
        reasons.append("healthy_pullback")
    if eod_bias == "SELL" and pullback_from_high_pct is not None and pullback_from_high_pct <= -0.02:
        score -= 0.6
        reasons.append("late_session_weakness")

    if eod_bias == "BUY" and day_change_pct is not None and day_change_pct >= 0.04:
        score -= 1.0
        reasons.append("chasing_penalty")
    if eod_bias == "SELL" and day_change_pct is not None and day_change_pct <= -0.04:
        score += 1.0
        reasons.append("oversold_sell_penalty")

    if eod_bias == "BUY" and rebound_from_low_pct is not None and rebound_from_low_pct >= 0.035:
        score -= 0.5
        reasons.append("extended_from_intraday_low")

    if review_gate == "REJECT":
        if eod_bias == "BUY":
            score -= 0.75
        elif eod_bias == "SELL":
            score += 0.75
        reasons.append("review_gate_reject")

    return round(float(score), 4), reasons


def _decision_signal(eod_bias: str, decision_score: float, review_gate: str, day_change_pct: float | None) -> str:
    if review_gate == "REJECT":
        return "HOLD"
    if eod_bias == "SELL" and day_change_pct is not None and day_change_pct <= -0.04:
        return "HOLD"
    if eod_bias == "BUY" and decision_score >= 4.0:
        return "BUY"
    if eod_bias == "SELL" and decision_score <= -4.0:
        return "SELL"
    return "HOLD"


def build_preclose_decisions(
    summary: pd.DataFrame,
    market_data_by_symbol: dict[str, pd.DataFrame],
    intraday_bars_by_symbol: dict[str, pd.DataFrame] | None = None,
    analysis_mode: PrecloseMode = "POST_CLOSE",
    signal_date: date | None = None,
    analysis_ts: datetime | None = None,
    fallback_symbols: list[str] | None = None,
) -> pd.DataFrame:
    if summary.empty and not fallback_symbols:
        return _empty_preclose_frame()

    base_summary = _ensure_preclose_summary_rows(summary, fallback_symbols=fallback_symbols)
    rows: list[dict[str, object]] = []
    ts_text = analysis_ts.isoformat() if analysis_ts is not None else ""
    signal_date_text = signal_date.isoformat() if signal_date is not None else ""
    intraday_map = intraday_bars_by_symbol or {}

    for _, base_row in base_summary.iterrows():
        symbol = str(base_row.get("symbol", ""))
        daily_frame = market_data_by_symbol.get(symbol, pd.DataFrame())
        metrics = _latest_bar_metrics(daily_frame, intraday_map.get(symbol))
        latest_price = metrics["latest_price"]
        prev_close = metrics["prev_close"]
        session_open = metrics["session_open"]
        session_high = metrics["session_high"]
        session_low = metrics["session_low"]
        ma20 = metrics["ma20"]
        ma60 = metrics["ma60"]
        day_change_pct = _pct_delta(latest_price, prev_close)
        pullback_from_high_pct = _pct_delta(latest_price, session_high)
        rebound_from_low_pct = _pct_delta(latest_price, session_low)
        distance_to_ma20_pct = _pct_delta(latest_price, ma20)
        distance_to_ma60_pct = _pct_delta(latest_price, ma60)
        trend_state = _trend_state(latest_price, ma20, ma60)

        row = base_row.copy()
        row["day_change_pct"] = day_change_pct
        row["pullback_from_high_pct"] = pullback_from_high_pct
        row["rebound_from_low_pct"] = rebound_from_low_pct
        row["distance_to_ma20_pct"] = distance_to_ma20_pct
        row["distance_to_ma60_pct"] = distance_to_ma60_pct
        row["trend_state"] = trend_state

        decision_score, reasons = _score_preclose_decision(row)
        decision_signal = _decision_signal(
            eod_bias=str(base_row.get("eod_bias", "HOLD")),
            decision_score=decision_score,
            review_gate=str(base_row.get("review_gate", "INSUFFICIENT_DATA")),
            day_change_pct=day_change_pct,
        )
        signal_context = {
            "eod_d": base_row.get("eod_d"),
            "eod_w": base_row.get("eod_w"),
            "eod_m": base_row.get("eod_m"),
            "intraday": base_row.get("intraday"),
            "eod_bias": base_row.get("eod_bias"),
            "alignment": base_row.get("alignment"),
            "secondary_action": base_row.get("secondary_action"),
            "secondary_confidence": base_row.get("secondary_confidence"),
            "review_gate": base_row.get("review_gate"),
            "review_score": base_row.get("review_score"),
            "composite_score": base_row.get("composite_score"),
            "dashboard_action": base_row.get("dashboard_action"),
        }
        if daily_frame.empty:
            decision_score = 0.0
            decision_signal = "HOLD"
            reasons = ["no_market_data"]
            signal_context = {
                "eod_d": "NO_DATA",
                "eod_w": "NO_DATA",
                "eod_m": "NO_DATA",
                "intraday": "NO_DATA",
                "eod_bias": "HOLD",
                "alignment": "NEUTRAL",
                "secondary_action": "HOLD_OBSERVE",
                "secondary_confidence": 50.0,
                "review_gate": "INSUFFICIENT_DATA",
                "review_score": 50.0,
                "composite_score": 0.0,
                "dashboard_action": "NEUTRAL",
            }

        rows.append(
            {
                "analysis_mode": analysis_mode,
                "analysis_ts": ts_text,
                "signal_date": signal_date_text,
                "symbol": symbol,
                "display_symbol": base_row.get("display_symbol"),
                "name": base_row.get("name"),
                "asset_type": base_row.get("asset_type"),
                "bucket": base_row.get("bucket"),
                "decision_signal": decision_signal,
                "decision_score": decision_score,
                "decision_reason": "|".join(reasons) if reasons else "summary_only",
                "trend_state": trend_state,
                "latest_price": latest_price,
                "prev_close": prev_close,
                "session_open": session_open,
                "session_high": session_high,
                "session_low": session_low,
                "day_change_pct": day_change_pct,
                "pullback_from_high_pct": pullback_from_high_pct,
                "rebound_from_low_pct": rebound_from_low_pct,
                "distance_to_ma20_pct": distance_to_ma20_pct,
                "distance_to_ma60_pct": distance_to_ma60_pct,
                **signal_context,
                "conviction_rank": base_row.get("conviction_rank"),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_preclose_frame()
    return frame.sort_values(["decision_score", "conviction_rank", "symbol"], ascending=[False, True, True]).reset_index(drop=True)


def _preclose_summary_payload(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "rows": int(len(frame.index)),
        "buy_count": int((frame.get("decision_signal") == "BUY").sum()) if not frame.empty else 0,
        "sell_count": int((frame.get("decision_signal") == "SELL").sum()) if not frame.empty else 0,
        "hold_count": int((frame.get("decision_signal") == "HOLD").sum()) if not frame.empty else 0,
        "top_symbols": frame.head(3)["symbol"].astype(str).tolist() if not frame.empty else [],
    }


def export_preclose_decisions(
    frame: pd.DataFrame,
    analysis_mode: PrecloseMode,
    signal_date: date,
    analysis_ts: datetime | None = None,
    output_dir: str | Path = "reports/preclose",
) -> dict[str, Path]:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = analysis_ts.strftime("%Y%m%d_%H%M") if analysis_ts is not None else signal_date.strftime("%Y%m%d")
    csv_path = folder / f"preclose_decision_{analysis_mode.lower()}_{suffix}.csv"
    json_path = folder / f"preclose_decision_{analysis_mode.lower()}_{suffix}.json"
    export_frame = frame.reindex(columns=PRE_CLOSE_COLUMNS)
    export_frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(
            {
                "analysis_mode": analysis_mode,
                "analysis_ts": analysis_ts.isoformat() if analysis_ts is not None else None,
                "signal_date": signal_date.isoformat(),
                "summary": _preclose_summary_payload(export_frame),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"csv_path": csv_path, "json_path": json_path}


def run_preclose_analysis(
    signal_ts: datetime | None = None,
    intraday_bar_frequency: str | None = None,
    use_intraday_snapshot: bool = False,
    output_dir: str | Path | None = None,
    config: PostgresConfig | None = None,
) -> dict[str, object]:
    runtime = load_runtime_config()
    universe = load_universe_config()
    universe_symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    target_ts = signal_ts
    target_date = resolve_preclose_signal_date(
        reference=signal_ts,
        runtime_config=runtime,
        use_intraday_snapshot=use_intraday_snapshot,
    )
    analysis_mode: PrecloseMode = "INTRADAY_PRE_CLOSE" if use_intraday_snapshot else "POST_CLOSE"
    bar_frequency = intraday_bar_frequency or runtime.intraday_bar_frequency
    target_output_dir = output_dir or runtime.preclose_output_dir

    with session_scope(config) as session:
        target_date_d = load_latest_signal_date_on_or_before(session, target_date, mode="eod", bar_frequency="D")
        eod_d = load_signals_by_date(session, target_date_d, mode="eod", bar_frequency="D") if target_date_d is not None else pd.DataFrame()
        target_date_w = load_latest_signal_date_on_or_before(session, target_date, mode="eod", bar_frequency="W")
        target_date_m = load_latest_signal_date_on_or_before(session, target_date, mode="eod", bar_frequency="M")
        eod_w = load_signals_by_date(session, target_date_w, mode="eod", bar_frequency="W") if target_date_w is not None else pd.DataFrame()
        eod_m = load_signals_by_date(session, target_date_m, mode="eod", bar_frequency="M") if target_date_m is not None else pd.DataFrame()
        market_data_by_symbol = load_market_prices_map(session, universe_symbols, limit=240, as_of_date=target_date) if universe_symbols else {}
        intraday = pd.DataFrame()
        intraday_bars_by_symbol: dict[str, pd.DataFrame] = {}
        if use_intraday_snapshot and target_ts is not None and universe_symbols:
            intraday = load_intraday_signals(session, signal_ts=target_ts, bar_frequency=bar_frequency)
            intraday_bars_by_symbol = load_realtime_bars_map(session, symbols=universe_symbols, bar_frequency=bar_frequency, limit=64)

    secondary_validation = build_secondary_validation(eod_d, market_data_by_symbol=market_data_by_symbol, signal_date=target_date)
    summary = build_signal_summary(
        eod_d=eod_d,
        eod_w=eod_w,
        eod_m=eod_m,
        intraday=intraday,
        secondary_validation=secondary_validation,
    )
    decisions = build_preclose_decisions(
        summary=summary,
        market_data_by_symbol=market_data_by_symbol,
        intraday_bars_by_symbol=intraday_bars_by_symbol,
        analysis_mode=analysis_mode,
        signal_date=target_date,
        analysis_ts=target_ts,
        fallback_symbols=universe_symbols,
    )
    exported = export_preclose_decisions(
        frame=decisions,
        analysis_mode=analysis_mode,
        signal_date=target_date,
        analysis_ts=target_ts,
        output_dir=target_output_dir,
    )
    return {
        "analysis_mode": analysis_mode,
        "signal_date": target_date.isoformat(),
        "analysis_ts": target_ts.isoformat() if target_ts is not None else None,
        "rows": int(len(decisions.index)),
        "csv_path": str(exported["csv_path"]),
        "json_path": str(exported["json_path"]),
        **_preclose_summary_payload(decisions),
    }
