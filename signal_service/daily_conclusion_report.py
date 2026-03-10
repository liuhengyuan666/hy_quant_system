from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from config.settings import PostgresConfig, RuntimeConfig, load_runtime_config, load_universe_config
from core.clock import now_shanghai
from core.trading_calendar import latest_closed_trading_date
from data_storage.database import session_scope
from data_storage.realtime_repository import load_intraday_signals, load_latest_intraday_signal_ts, load_realtime_bars_map
from data_storage.repository import load_latest_signal_date, load_latest_signal_date_on_or_before, load_market_prices_map, load_signals_by_date
from signal_service.preclose_decision import build_preclose_decisions
from signal_service.secondary_validation import build_secondary_validation
from signal_service.summary_view import build_signal_summary
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names
from strategy_engine.library import MARKET_HYPOTHESIS_ORDER, build_strategy_specs, market_hypothesis_label

ACTION_COLUMNS = ["long_term_action", "short_term_action", "preclose_signal", "overall_action"]
OPERATION_VIEW_COLUMNS = [
    "conviction_rank",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "long_term_action",
    "short_term_action",
    "hypothesis_consensus_action",
    "hypothesis_summary_text",
    "preclose_signal",
    "overall_action",
    "action_note",
    "data_status",
]
DAILY_CONCLUSION_COLUMNS = [
    "conviction_rank",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "data_status",
    "long_term_action",
    "long_term_score",
    "long_term_confidence",
    "long_term_buy_count",
    "long_term_hold_count",
    "long_term_sell_count",
    "long_term_supporting_evidence",
    "short_term_action",
    "short_term_score",
    "short_term_confidence",
    "short_term_buy_count",
    "short_term_hold_count",
    "short_term_sell_count",
    "short_term_supporting_evidence",
    "hypothesis_consensus_action",
    "hypothesis_consensus_score",
    "hypothesis_consensus_confidence",
    "hypothesis_active_group_count",
    "hypothesis_consensus_supporting_evidence",
    "hypothesis_summary_text",
    "hypothesis_tiebreak_applied",
    "preclose_signal",
    "preclose_score",
    "overall_action",
    "dashboard_action",
    "eod_bias",
    "alignment",
]
EVIDENCE_COLUMNS = [
    "symbol",
    "name",
    "horizon",
    "market_hypothesis",
    "market_hypothesis_label",
    "source",
    "strategy",
    "signal",
    "weight",
    "weighted_score",
]
HYPOTHESIS_SUMMARY_COLUMNS = [
    "conviction_rank",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "horizon",
    "market_hypothesis",
    "market_hypothesis_label",
    "hypothesis_action",
    "hypothesis_score",
    "hypothesis_confidence",
    "hypothesis_strategy_count",
    "hypothesis_buy_count",
    "hypothesis_hold_count",
    "hypothesis_sell_count",
    "hypothesis_supporting_evidence",
]
DATA_GAP_COLUMNS = ["symbol", "display_symbol", "name", "asset_type", "bucket", "issue_type", "reason"]
ASSET_TYPE_ORDER = {"INDEX": 0, "ETF": 1}
HORIZON_ORDER = {"long_term": 0, "short_term": 1}
HYPOTHESIS_ORDER = {value: index for index, value in enumerate(MARKET_HYPOTHESIS_ORDER)}
DATA_STATUS_ORDER = {"OK": 0, "PARTIAL": 1, "NO_DATA": 2}
ACTION_PRIORITY_ORDER = {
    "ALIGNED_ACTION": 0,
    "ONE_SIDED_ACTION": 1,
    "CONFLICT": 2,
    "PRECLOSE_ALERT": 3,
    "WAIT": 4,
    "NO_DATA": 5,
}
ACTION_ALIGNMENT_ORDER = {
    "BUY_BUY": 0,
    "SELL_SELL": 1,
    "BUY_HOLD": 2,
    "SELL_HOLD": 3,
    "HOLD_BUY": 4,
    "HOLD_SELL": 5,
    "BUY_SELL": 6,
    "SELL_BUY": 7,
    "HOLD_HOLD": 8,
    "NO_DATA": 9,
}
LONG_TERM_SOURCE_WEIGHTS = {"EOD_D": 1.0, "EOD_W": 1.5, "EOD_M": 2.0}
SHORT_TERM_SOURCE_WEIGHTS = {"EOD_D": 1.0, "INTRADAY": 1.2}
ACTION_COUNT_ORDER = ["BUY", "SELL", "HOLD", "NO_DATA", "MISSING"]
PRECLOSE_COUNT_ORDER = ["BUY", "SELL", "HOLD"]
SECTOR_KEYWORDS = {"银行", "券商", "有色", "通信", "电力"}
THEME_KEYWORDS = {"人工智能", "金融科技", "科技", "AH股", "科创"}


def _resolve_excel_engine() -> Literal["xlsxwriter"]:
    if importlib.util.find_spec("xlsxwriter") is not None:
        return "xlsxwriter"
    raise ImportError("xlsxwriter is required for daily conclusion Excel export. Install dependencies from requirements.txt")


def _normalize_signal(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"BUY", "SELL", "HOLD"}:
        return text
    return "HOLD"


def _signal_score(signal: str) -> float:
    if signal == "BUY":
        return 1.0
    if signal == "SELL":
        return -1.0
    return 0.0


def _safe_float(value: object, default: float = 0.0) -> float:
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "nat", "none", "<na>"}:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int = 0) -> int:
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "nat", "none", "<na>"}:
        return default
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _hypothesis_weight(runtime_config: RuntimeConfig, market_hypothesis: str) -> float:
    weights = runtime_config.hypothesis_weights or {}
    return _safe_float(weights.get(market_hypothesis), default=1.0)


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


def _sort_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return frame.copy()
    table = frame.copy()
    if "asset_type" not in table.columns:
        table["asset_type"] = pd.Series(dtype="string")
    if "bucket" not in table.columns:
        table["bucket"] = pd.Series(dtype="string")
    if "conviction_rank" not in table.columns:
        table["conviction_rank"] = pd.Series(dtype="float64")
    table["_asset_type_order"] = table["asset_type"].astype(str).map(ASSET_TYPE_ORDER).fillna(99)
    table["_bucket_order"] = table["bucket"].fillna("未分组").astype(str)
    table["_rank_order"] = pd.to_numeric(table["conviction_rank"], errors="coerce").fillna(999999)
    table["_symbol_order"] = table["symbol"].astype(str)
    ordered = table.sort_values(
        ["_asset_type_order", "_bucket_order", "_rank_order", "_symbol_order"],
        ascending=[True, True, True, True],
    ).reset_index(drop=True)
    return ordered.drop(columns=["_asset_type_order", "_bucket_order", "_rank_order", "_symbol_order"])


def _operation_alignment_key(long_term_action: str, short_term_action: str, data_status: str) -> str:
    if data_status == "NO_DATA":
        return "NO_DATA"
    return f"{long_term_action}_{short_term_action}"


def _operation_priority_key(
    long_term_action: str,
    short_term_action: str,
    overall_action: str,
    preclose_signal: str,
    data_status: str,
) -> str:
    if data_status == "NO_DATA":
        return "NO_DATA"
    actionable = {"BUY", "SELL"}
    if long_term_action == short_term_action and long_term_action in actionable:
        return "ALIGNED_ACTION"
    if (long_term_action in actionable and short_term_action == "HOLD") or (
        short_term_action in actionable and long_term_action == "HOLD"
    ):
        return "ONE_SIDED_ACTION"
    if {long_term_action, short_term_action} == actionable:
        return "CONFLICT"
    if overall_action == "HOLD" and preclose_signal in actionable:
        return "PRECLOSE_ALERT"
    return "WAIT"


def _sort_operation_view(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return frame.copy()
    table = frame.copy()
    if "overall_action" not in table.columns:
        table["overall_action"] = pd.Series(dtype="string")
    if "data_status" not in table.columns:
        table["data_status"] = pd.Series(dtype="string")
    if "long_term_action" not in table.columns:
        table["long_term_action"] = pd.Series(dtype="string")
    if "short_term_action" not in table.columns:
        table["short_term_action"] = pd.Series(dtype="string")
    if "preclose_signal" not in table.columns:
        table["preclose_signal"] = pd.Series(dtype="string")
    if "conviction_rank" not in table.columns:
        table["conviction_rank"] = pd.Series(dtype="float64")
    if "asset_type" not in table.columns:
        table["asset_type"] = pd.Series(dtype="string")
    if "bucket" not in table.columns:
        table["bucket"] = pd.Series(dtype="string")

    alignment = table.apply(
        lambda row: _operation_alignment_key(
            str(row.get("long_term_action", "HOLD")),
            str(row.get("short_term_action", "HOLD")),
            str(row.get("data_status", "OK")),
        ),
        axis=1,
    )
    priority = table.apply(
        lambda row: _operation_priority_key(
            str(row.get("long_term_action", "HOLD")),
            str(row.get("short_term_action", "HOLD")),
            str(row.get("overall_action", "HOLD")),
            str(row.get("preclose_signal", "HOLD")),
            str(row.get("data_status", "OK")),
        ),
        axis=1,
    )
    table["_data_status_order"] = table["data_status"].astype(str).map(DATA_STATUS_ORDER).fillna(99)
    table["_priority_order"] = priority.map(ACTION_PRIORITY_ORDER).fillna(99)
    table["_alignment_order"] = alignment.map(ACTION_ALIGNMENT_ORDER).fillna(99)
    table["_preclose_order"] = table["preclose_signal"].astype(str).map({"BUY": 0, "SELL": 1, "HOLD": 2}).fillna(9)
    table["_rank_order"] = pd.to_numeric(table["conviction_rank"], errors="coerce").fillna(999999)
    table["_asset_type_order"] = table["asset_type"].astype(str).map(ASSET_TYPE_ORDER).fillna(99)
    table["_bucket_order"] = table["bucket"].fillna("未分组").astype(str)
    table["_symbol_order"] = table["symbol"].astype(str)
    ordered = table.sort_values(
        [
            "_data_status_order",
            "_priority_order",
            "_alignment_order",
            "_preclose_order",
            "_rank_order",
            "_asset_type_order",
            "_bucket_order",
            "_symbol_order",
        ],
        ascending=[True, True, True, True, True, True, True, True],
    ).reset_index(drop=True)
    return ordered.drop(
        columns=[
            "_data_status_order",
            "_priority_order",
            "_alignment_order",
            "_preclose_order",
            "_rank_order",
            "_asset_type_order",
            "_bucket_order",
            "_symbol_order",
        ]
    )


def _overview_count_rows(frame: pd.DataFrame, column: str, section: str, value_order: list[str]) -> list[dict[str, str]]:
    if frame.empty or column not in frame.columns:
        return [{"section": section, "item": value, "value": "0"} for value in value_order]
    counts = frame[column].astype(str).value_counts(dropna=False)
    return [{"section": section, "item": value, "value": str(int(counts.get(value, 0)))} for value in value_order]


def _build_fallback_rows(symbols: list[str], start_rank: int = 1) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame(columns=["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket", "dashboard_action", "eod_bias", "alignment"])
    rows = pd.DataFrame({"symbol": symbols})
    rows = enrich_signal_frame_with_symbol_names(rows)
    rows["asset_type"] = rows["display_symbol"].map(_classify_asset_type)
    rows["bucket"] = rows.apply(lambda row: _classify_bucket(row.get("name"), row.get("asset_type")), axis=1)
    rows["conviction_rank"] = pd.RangeIndex(start=start_rank, stop=start_rank + len(rows.index))
    rows["dashboard_action"] = pd.Series(dtype="string")
    rows["eod_bias"] = pd.Series(dtype="string")
    rows["alignment"] = pd.Series(dtype="string")
    return rows


def _build_base_rows(summary: pd.DataFrame, fallback_symbols: list[str] | None = None) -> pd.DataFrame:
    required = ["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket", "dashboard_action", "eod_bias", "alignment"]
    if not summary.empty:
        table = summary.copy()
        for column in required:
            if column not in table.columns:
                table[column] = pd.Series(dtype="string")
        missing_symbols = sorted(set(fallback_symbols or []) - set(table["symbol"].astype(str).tolist()))
        if missing_symbols:
            existing_ranks = pd.to_numeric(table["conviction_rank"], errors="coerce")
            next_rank = int(existing_ranks.max()) + 1 if not existing_ranks.dropna().empty else 1
            fallback_rows = _build_fallback_rows(missing_symbols, start_rank=next_rank)
            table = pd.concat([table[required], fallback_rows[required]], ignore_index=True)
        return _sort_rows(table[required])

    symbols = sorted(set(fallback_symbols or []))
    if not symbols:
        return pd.DataFrame(columns=["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket", "dashboard_action", "eod_bias", "alignment"])
    return _sort_rows(_build_fallback_rows(symbols, start_rank=1))


def _resolve_eod_signal_dates(session, requested_date: date | None = None) -> dict[str, date | None]:
    daily_date = (
        load_latest_signal_date_on_or_before(session, requested_date, mode="eod", bar_frequency="D")
        if requested_date is not None
        else load_latest_signal_date(session, mode="eod", bar_frequency="D")
    )
    reference_date = daily_date or requested_date or latest_closed_trading_date()
    weekly_date = load_latest_signal_date_on_or_before(session, reference_date, mode="eod", bar_frequency="W")
    monthly_date = load_latest_signal_date_on_or_before(session, reference_date, mode="eod", bar_frequency="M")
    return {"D": daily_date, "W": weekly_date, "M": monthly_date}


def _build_strategy_evidence(
    eod_d: pd.DataFrame,
    eod_w: pd.DataFrame,
    eod_m: pd.DataFrame,
    intraday: pd.DataFrame,
) -> pd.DataFrame:
    spec_by_name = {item.name: item for item in build_strategy_specs()}
    rows: list[dict[str, object]] = []
    sources = [
        (eod_d, "EOD_D", LONG_TERM_SOURCE_WEIGHTS["EOD_D"]),
        (eod_w, "EOD_W", LONG_TERM_SOURCE_WEIGHTS["EOD_W"]),
        (eod_m, "EOD_M", LONG_TERM_SOURCE_WEIGHTS["EOD_M"]),
        (intraday, "INTRADAY", SHORT_TERM_SOURCE_WEIGHTS["INTRADAY"]),
    ]
    for frame, source, source_weight in sources:
        if frame.empty:
            continue
        table = frame.copy()
        if "symbol" not in table.columns or "strategy" not in table.columns or "signal" not in table.columns:
            continue
        table["symbol"] = table["symbol"].astype(str)
        table["strategy"] = table["strategy"].astype(str)
        table["signal"] = table["signal"].map(_normalize_signal)
        for _, row in table.iterrows():
            strategy_name = str(row.get("strategy", ""))
            spec = spec_by_name.get(strategy_name)
            if spec is None:
                continue
            if source == "INTRADAY" and "intraday" not in spec.supported_modes:
                continue
            if source != "INTRADAY" and "eod" not in spec.supported_modes:
                continue
            if spec.horizon == "long_term" and source == "INTRADAY":
                continue
            if spec.horizon == "short_term" and source in {"EOD_W", "EOD_M"}:
                continue
            signal = str(row.get("signal", "HOLD"))
            weight = float(source_weight * spec.report_weight)
            rows.append(
                {
                    "symbol": str(row.get("symbol", "")),
                    "strategy": strategy_name,
                    "horizon": spec.horizon,
                    "market_hypothesis": spec.market_hypothesis,
                    "market_hypothesis_label": market_hypothesis_label(spec.market_hypothesis),
                    "source": source,
                    "signal": signal,
                    "weight": weight,
                    "weighted_score": float(weight * _signal_score(signal)),
                }
            )
    return pd.DataFrame(rows)


def _supporting_evidence_text(frame: pd.DataFrame, action: str) -> str:
    if frame.empty:
        return "NONE"
    if action in {"BUY", "SELL", "HOLD"}:
        matched = frame[frame["signal"] == action].copy()
        if not matched.empty:
            matched = matched.sort_values(["weight", "source", "strategy"], ascending=[False, True, True])
            labels: list[str] = []
            seen: set[str] = set()
            for _, row in matched.iterrows():
                label = f"{row['strategy']}@{row['source']}"
                if label in seen:
                    continue
                seen.add(label)
                labels.append(label)
            return " | ".join(labels[:6]) if labels else "NONE"
    buy_weight = float(frame.loc[frame["signal"] == "BUY", "weight"].sum())
    sell_weight = float(frame.loc[frame["signal"] == "SELL", "weight"].sum())
    if buy_weight == sell_weight and buy_weight > 0:
        return "balanced_buy_sell"
    return "mixed_signals"


def _empty_aggregate(prefix: str, action: str, reason: str) -> dict[str, object]:
    return {
        f"{prefix}_action": action,
        f"{prefix}_score": None,
        f"{prefix}_confidence": None,
        f"{prefix}_strategy_count": 0,
        f"{prefix}_buy_count": 0,
        f"{prefix}_hold_count": 0,
        f"{prefix}_sell_count": 0,
        f"{prefix}_supporting_evidence": reason,
    }


def _aggregate_scoped_evidence(scoped: pd.DataFrame, prefix: str) -> dict[str, object]:
    if scoped.empty:
        return _empty_aggregate(prefix, action="MISSING", reason="missing_strategy_signals")

    buy_count = int((scoped["signal"] == "BUY").sum())
    hold_count = int((scoped["signal"] == "HOLD").sum())
    sell_count = int((scoped["signal"] == "SELL").sum())
    buy_weight = float(scoped.loc[scoped["signal"] == "BUY", "weight"].sum())
    hold_weight = float(scoped.loc[scoped["signal"] == "HOLD", "weight"].sum())
    sell_weight = float(scoped.loc[scoped["signal"] == "SELL", "weight"].sum())
    total_weight = buy_weight + hold_weight + sell_weight
    if total_weight <= 0:
        return _empty_aggregate(prefix, action="MISSING", reason="missing_strategy_signals") | {
            f"{prefix}_strategy_count": int(scoped["strategy"].nunique()),
            f"{prefix}_buy_count": buy_count,
            f"{prefix}_hold_count": hold_count,
            f"{prefix}_sell_count": sell_count,
        }

    net_score = float((buy_weight - sell_weight) / total_weight)
    dominant_weight = max(buy_weight, hold_weight, sell_weight)
    confidence = float(dominant_weight / total_weight)
    if buy_weight > sell_weight and net_score >= 0.20:
        action = "BUY"
    elif sell_weight > buy_weight and net_score <= -0.20:
        action = "SELL"
    else:
        action = "HOLD"

    return {
        f"{prefix}_action": action,
        f"{prefix}_score": round(net_score, 4),
        f"{prefix}_confidence": round(confidence, 4),
        f"{prefix}_strategy_count": int(scoped["strategy"].nunique()),
        f"{prefix}_buy_count": buy_count,
        f"{prefix}_hold_count": hold_count,
        f"{prefix}_sell_count": sell_count,
        f"{prefix}_supporting_evidence": _supporting_evidence_text(scoped, action),
    }


def _aggregate_horizon(symbol: str, horizon: str, evidence: pd.DataFrame, no_data_symbols: set[str]) -> dict[str, object]:
    prefix = f"{horizon}_"
    if symbol in no_data_symbols:
        return _empty_aggregate(prefix.rstrip("_"), action="NO_DATA", reason="no_market_data")

    scoped = evidence[(evidence["symbol"] == symbol) & (evidence["horizon"] == horizon)].copy()
    aggregate = _aggregate_scoped_evidence(scoped, prefix.rstrip("_"))
    return {
        f"{prefix}action": aggregate[f"{prefix.rstrip('_')}_action"],
        f"{prefix}score": aggregate[f"{prefix.rstrip('_')}_score"],
        f"{prefix}confidence": aggregate[f"{prefix.rstrip('_')}_confidence"],
        f"{prefix}buy_count": aggregate[f"{prefix.rstrip('_')}_buy_count"],
        f"{prefix}hold_count": aggregate[f"{prefix.rstrip('_')}_hold_count"],
        f"{prefix}sell_count": aggregate[f"{prefix.rstrip('_')}_sell_count"],
        f"{prefix}supporting_evidence": aggregate[f"{prefix.rstrip('_')}_supporting_evidence"],
    }


def _sort_hypothesis_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return frame.copy()

    table = frame.copy()
    table["_asset_type_order"] = table["asset_type"].astype(str).map(ASSET_TYPE_ORDER).fillna(99)
    table["_bucket_order"] = table["bucket"].fillna("未分组").astype(str)
    table["_rank_order"] = pd.to_numeric(table["conviction_rank"], errors="coerce").fillna(999999)
    table["_horizon_order"] = table["horizon"].astype(str).map(HORIZON_ORDER).fillna(99)
    table["_hypothesis_order"] = table["market_hypothesis"].astype(str).map(HYPOTHESIS_ORDER).fillna(99)
    table["_symbol_order"] = table["symbol"].astype(str)
    ordered = table.sort_values(
        ["_asset_type_order", "_bucket_order", "_rank_order", "_horizon_order", "_hypothesis_order", "_symbol_order"],
        ascending=[True, True, True, True, True, True],
    ).reset_index(drop=True)
    return ordered.drop(columns=["_asset_type_order", "_bucket_order", "_rank_order", "_horizon_order", "_hypothesis_order", "_symbol_order"])


def build_hypothesis_summary_frame(
    summary: pd.DataFrame,
    long_term_evidence: pd.DataFrame,
    short_term_evidence: pd.DataFrame,
    market_data_by_symbol: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=HYPOTHESIS_SUMMARY_COLUMNS)

    evidence = pd.concat([long_term_evidence, short_term_evidence], ignore_index=True)
    if evidence.empty:
        return pd.DataFrame(columns=HYPOTHESIS_SUMMARY_COLUMNS)

    base_rows = summary[["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket"]].copy()
    base_rows["symbol"] = base_rows["symbol"].astype(str)
    no_data_symbols = {symbol for symbol, frame in (market_data_by_symbol or {}).items() if frame.empty}
    rows: list[dict[str, object]] = []
    for (symbol, horizon, market_hypothesis), scoped in evidence.groupby(["symbol", "horizon", "market_hypothesis"], dropna=False):
        meta_match = base_rows[base_rows["symbol"] == str(symbol)]
        if meta_match.empty:
            continue
        meta = meta_match.iloc[0]
        aggregate = (
            _empty_aggregate("hypothesis", action="NO_DATA", reason="no_market_data")
            if str(symbol) in no_data_symbols
            else _aggregate_scoped_evidence(scoped.copy(), "hypothesis")
        )
        rows.append(
            {
                "conviction_rank": meta.get("conviction_rank"),
                "symbol": str(symbol),
                "display_symbol": meta.get("display_symbol"),
                "name": meta.get("name"),
                "asset_type": meta.get("asset_type"),
                "bucket": meta.get("bucket"),
                "horizon": str(horizon),
                "market_hypothesis": str(market_hypothesis),
                "market_hypothesis_label": market_hypothesis_label(str(market_hypothesis)),
                **aggregate,
            }
        )

    hypothesis_summary = pd.DataFrame(rows)
    if hypothesis_summary.empty:
        return pd.DataFrame(columns=HYPOTHESIS_SUMMARY_COLUMNS)
    for column in HYPOTHESIS_SUMMARY_COLUMNS:
        if column not in hypothesis_summary.columns:
            hypothesis_summary[column] = pd.Series(dtype="string")
    return _sort_hypothesis_summary(hypothesis_summary[HYPOTHESIS_SUMMARY_COLUMNS])


def _hypothesis_supporting_text(frame: pd.DataFrame, action: str) -> str:
    if frame.empty or action not in {"BUY", "SELL"}:
        return "mixed_hypothesis_signals"

    matched = frame[frame["hypothesis_action"].astype(str) == action].copy()
    if matched.empty:
        return "mixed_hypothesis_signals"

    matched["strength"] = pd.to_numeric(matched["hypothesis_score"], errors="coerce").abs().fillna(0.0) * pd.to_numeric(
        matched["hypothesis_confidence"], errors="coerce"
    ).fillna(0.0)
    matched = matched.sort_values(["strength", "horizon", "market_hypothesis"], ascending=[False, True, True])
    labels: list[str] = []
    seen: set[str] = set()
    for _, row in matched.iterrows():
        label = f"{row['market_hypothesis_label']}@{row['horizon']}"
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return " | ".join(labels[:6]) if labels else "mixed_hypothesis_signals"


def _build_hypothesis_consensus_lookup(hypothesis_summary: pd.DataFrame, runtime_config: RuntimeConfig) -> dict[str, dict[str, object]]:
    if hypothesis_summary.empty or "symbol" not in hypothesis_summary.columns:
        return {}

    lookup: dict[str, dict[str, object]] = {}
    for symbol, subset in hypothesis_summary.groupby("symbol", dropna=False):
        table = subset.copy()
        scores = pd.to_numeric(table["hypothesis_score"], errors="coerce").fillna(0.0)
        confidences = pd.to_numeric(table["hypothesis_confidence"], errors="coerce").fillna(0.0)
        actions = table["hypothesis_action"].astype(str)
        hypothesis_weights = table["market_hypothesis"].astype(str).map(lambda name: _hypothesis_weight(runtime_config, name))
        strengths = scores.abs() * confidences * hypothesis_weights
        buy_strength = float(strengths[actions == "BUY"].sum())
        sell_strength = float(strengths[actions == "SELL"].sum())
        hold_strength = float((confidences * hypothesis_weights)[actions == "HOLD"].sum())
        active_group_count = int(
            table.loc[actions.isin(["BUY", "SELL"]), "market_hypothesis"].astype(str).nunique()
        )
        total_strength = buy_strength + sell_strength + hold_strength
        if total_strength <= 0:
            lookup[str(symbol)] = {
                "hypothesis_consensus_action": "HOLD",
                "hypothesis_consensus_score": 0.0,
                "hypothesis_consensus_confidence": 0.0,
                "hypothesis_active_group_count": active_group_count,
                "hypothesis_consensus_supporting_evidence": "mixed_hypothesis_signals",
            }
            continue

        net_score = float((buy_strength - sell_strength) / total_strength)
        dominant_strength = max(buy_strength, sell_strength, hold_strength)
        confidence = float(dominant_strength / total_strength)
        if buy_strength > sell_strength and net_score >= 0.15:
            action = "BUY"
        elif sell_strength > buy_strength and net_score <= -0.15:
            action = "SELL"
        else:
            action = "HOLD"
        lookup[str(symbol)] = {
            "hypothesis_consensus_action": action,
            "hypothesis_consensus_score": round(net_score, 4),
            "hypothesis_consensus_confidence": round(confidence, 4),
            "hypothesis_active_group_count": active_group_count,
            "hypothesis_consensus_supporting_evidence": _hypothesis_supporting_text(table, action),
        }
    return lookup


def _resolve_overall_action_with_hypothesis(
    long_term_action: str,
    short_term_action: str,
    data_status: str,
    hypothesis_consensus: dict[str, object],
    runtime_config: RuntimeConfig,
) -> tuple[str, bool]:
    base_action = _overall_action(long_term_action, short_term_action, data_status)
    if data_status != "OK":
        return base_action, False

    consensus_action = str(hypothesis_consensus.get("hypothesis_consensus_action", "HOLD"))
    if consensus_action not in {"BUY", "SELL"}:
        return base_action, False

    score = _safe_float(hypothesis_consensus.get("hypothesis_consensus_score"), default=0.0)
    confidence = _safe_float(hypothesis_consensus.get("hypothesis_consensus_confidence"), default=0.0)
    active_group_count = _safe_int(hypothesis_consensus.get("hypothesis_active_group_count"), default=0)
    if score is None or confidence is None or active_group_count < runtime_config.hypothesis_tiebreak_min_groups:
        return base_action, False

    numeric_score = abs(score)
    numeric_confidence = confidence
    if {long_term_action, short_term_action} == {"BUY", "SELL"}:
        if numeric_score >= runtime_config.hypothesis_conflict_min_score and numeric_confidence >= runtime_config.hypothesis_conflict_min_confidence:
            return consensus_action, True
        return base_action, False

    if long_term_action == short_term_action == "HOLD":
        if numeric_score >= runtime_config.hypothesis_hold_min_score and numeric_confidence >= runtime_config.hypothesis_hold_min_confidence:
            return consensus_action, True
    return base_action, False


def _hypothesis_summary_text(row: dict[str, object]) -> str:
    consensus_action = str(row.get("hypothesis_consensus_action", "HOLD"))
    tiebreak_applied = bool(row.get("hypothesis_tiebreak_applied", False))
    active_group_count = _safe_int(row.get("hypothesis_active_group_count"), default=0)
    support = str(row.get("hypothesis_consensus_supporting_evidence", "mixed_hypothesis_signals"))
    if consensus_action in {"BUY", "SELL"}:
        if tiebreak_applied:
            return f"分组共识改判为 {consensus_action}（{active_group_count} 组；{support}）"
        return f"分组共识偏向 {consensus_action}（{active_group_count} 组；{support}）"
    if active_group_count > 0:
        return f"分组共识仍观望（{active_group_count} 组活跃；{support}）"
    return "暂无有效分组共识"


def _overall_action(long_term_action: str, short_term_action: str, data_status: str) -> str:
    if data_status == "NO_DATA":
        return "NO_DATA"
    actionable = {"BUY", "SELL"}
    if long_term_action == short_term_action and long_term_action in actionable:
        return long_term_action
    if long_term_action in actionable and short_term_action == "HOLD":
        return long_term_action
    if short_term_action in actionable and long_term_action == "HOLD":
        return short_term_action
    if long_term_action == "HOLD" and short_term_action == "HOLD":
        return "HOLD"
    return "HOLD"


def _operation_note(row: pd.Series) -> str:
    data_status = str(row.get("data_status", "OK"))
    long_term_action = str(row.get("long_term_action", "HOLD"))
    short_term_action = str(row.get("short_term_action", "HOLD"))
    preclose_signal = str(row.get("preclose_signal", "HOLD"))
    overall_action = str(row.get("overall_action", "HOLD"))
    hypothesis_consensus_action = str(row.get("hypothesis_consensus_action", "HOLD"))
    hypothesis_tiebreak_applied = bool(row.get("hypothesis_tiebreak_applied", False))

    if data_status == "NO_DATA":
        return "缺少历史行情，暂不判断"
    if data_status == "PARTIAL":
        return "部分策略信号缺失，结论仅供参考"
    if hypothesis_tiebreak_applied and {long_term_action, short_term_action} == {"BUY", "SELL"}:
        return f"分组共识偏向 {hypothesis_consensus_action}，用于化解长短线冲突"
    if hypothesis_tiebreak_applied and long_term_action == short_term_action == "HOLD":
        return f"长短线均观望，但策略分组共识转为 {hypothesis_consensus_action}"
    if long_term_action == short_term_action == "BUY":
        return "长短线同向看多"
    if long_term_action == short_term_action == "SELL":
        return "长短线同向看空"
    if long_term_action == "BUY" and short_term_action == "HOLD":
        return "长线偏多，短线等待"
    if long_term_action == "SELL" and short_term_action == "HOLD":
        return "长线偏空，短线等待"
    if long_term_action == "HOLD" and short_term_action == "BUY":
        return "短线偏多，长线未确认"
    if long_term_action == "HOLD" and short_term_action == "SELL":
        return "短线偏空，长线未确认"
    if {long_term_action, short_term_action} == {"BUY", "SELL"}:
        return "长短线分歧，谨慎处理"
    if overall_action == "HOLD" and preclose_signal in {"BUY", "SELL"}:
        return f"收盘前提示 {preclose_signal}，但主结论仍观望"
    return "维持观望"


def build_operation_view(conclusion: pd.DataFrame) -> pd.DataFrame:
    if conclusion.empty:
        return pd.DataFrame(columns=OPERATION_VIEW_COLUMNS)
    view = conclusion.copy()
    view["action_note"] = view.apply(_operation_note, axis=1)
    for column in OPERATION_VIEW_COLUMNS:
        if column not in view.columns:
            view[column] = pd.Series(dtype="string")
    return _sort_operation_view(view[OPERATION_VIEW_COLUMNS])


def build_daily_conclusions(
    summary: pd.DataFrame,
    eod_d: pd.DataFrame,
    eod_w: pd.DataFrame,
    eod_m: pd.DataFrame,
    intraday: pd.DataFrame,
    preclose: pd.DataFrame,
    market_data_by_symbol: dict[str, pd.DataFrame] | None = None,
    fallback_symbols: list[str] | None = None,
    runtime_config: RuntimeConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    config = runtime_config or load_runtime_config()
    base_symbols = [
        str(symbol)
        for symbol in sorted(
        {
            *(fallback_symbols or []),
            *eod_d.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
            *eod_w.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
            *eod_m.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
            *intraday.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
            *preclose.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
        }
        )
    ]
    base_rows = _build_base_rows(summary, fallback_symbols=base_symbols)
    evidence = _build_strategy_evidence(eod_d=eod_d, eod_w=eod_w, eod_m=eod_m, intraday=intraday)
    if not base_rows.empty and "name" in base_rows.columns:
        evidence = evidence.merge(base_rows[["symbol", "name"]], on="symbol", how="left") if not evidence.empty else pd.DataFrame(columns=EVIDENCE_COLUMNS)
    if not evidence.empty:
        for column in EVIDENCE_COLUMNS:
            if column not in evidence.columns:
                evidence[column] = pd.Series(dtype="string")
        evidence = evidence[EVIDENCE_COLUMNS].sort_values(["symbol", "horizon", "source", "strategy"], ascending=[True, True, True, True]).reset_index(drop=True)
    else:
        evidence = pd.DataFrame(columns=EVIDENCE_COLUMNS)

    long_term_evidence = evidence[evidence["horizon"] == "long_term"].reset_index(drop=True) if not evidence.empty else pd.DataFrame(columns=EVIDENCE_COLUMNS)
    short_term_evidence = evidence[evidence["horizon"] == "short_term"].reset_index(drop=True) if not evidence.empty else pd.DataFrame(columns=EVIDENCE_COLUMNS)
    hypothesis_summary = build_hypothesis_summary_frame(
        summary=base_rows,
        long_term_evidence=long_term_evidence,
        short_term_evidence=short_term_evidence,
        market_data_by_symbol=market_data_by_symbol,
    )
    hypothesis_consensus_lookup = _build_hypothesis_consensus_lookup(hypothesis_summary, runtime_config=config)

    no_data_symbols = {symbol for symbol, frame in (market_data_by_symbol or {}).items() if frame.empty}
    preclose_lookup = {}
    if not preclose.empty and "symbol" in preclose.columns:
        for _, row in preclose.iterrows():
            preclose_lookup[str(row.get("symbol", ""))] = {
                "preclose_signal": str(row.get("decision_signal", "HOLD")),
                "preclose_score": pd.to_numeric([row.get("decision_score")], errors="coerce")[0],
            }

    rows: list[dict[str, object]] = []
    data_gap_rows: list[dict[str, object]] = []
    for _, row in base_rows.iterrows():
        symbol = str(row.get("symbol", ""))
        long_term = _aggregate_horizon(symbol, "long_term", evidence, no_data_symbols)
        short_term = _aggregate_horizon(symbol, "short_term", evidence, no_data_symbols)
        preclose_info = preclose_lookup.get(symbol, {"preclose_signal": "HOLD", "preclose_score": None})
        data_status = "NO_DATA" if symbol in no_data_symbols else "PARTIAL" if "MISSING" in {str(long_term["long_term_action"]), str(short_term["short_term_action"])} else "OK"
        hypothesis_consensus = hypothesis_consensus_lookup.get(
            symbol,
            {
                "hypothesis_consensus_action": "HOLD",
                "hypothesis_consensus_score": 0.0,
                "hypothesis_consensus_confidence": 0.0,
                "hypothesis_active_group_count": 0,
                "hypothesis_consensus_supporting_evidence": "mixed_hypothesis_signals",
            },
        )
        resolved_overall_action, hypothesis_tiebreak_applied = _resolve_overall_action_with_hypothesis(
            long_term_action=str(long_term["long_term_action"]),
            short_term_action=str(short_term["short_term_action"]),
            data_status=data_status,
            hypothesis_consensus=hypothesis_consensus,
            runtime_config=config,
        )
        result_row = {
            "conviction_rank": row.get("conviction_rank"),
            "symbol": symbol,
            "display_symbol": row.get("display_symbol"),
            "name": row.get("name"),
            "asset_type": row.get("asset_type"),
            "bucket": row.get("bucket"),
            "data_status": data_status,
            **long_term,
            **short_term,
            **hypothesis_consensus,
            "hypothesis_tiebreak_applied": hypothesis_tiebreak_applied,
            "preclose_signal": preclose_info.get("preclose_signal"),
            "preclose_score": None if pd.isna(preclose_info.get("preclose_score")) else float(preclose_info.get("preclose_score")),
            "overall_action": resolved_overall_action,
            "dashboard_action": row.get("dashboard_action"),
            "eod_bias": row.get("eod_bias"),
            "alignment": row.get("alignment"),
        }
        result_row["hypothesis_summary_text"] = _hypothesis_summary_text(result_row)
        rows.append(result_row)
        if data_status != "OK":
            data_gap_rows.append(
                {
                    "symbol": symbol,
                    "display_symbol": row.get("display_symbol"),
                    "name": row.get("name"),
                    "asset_type": row.get("asset_type"),
                    "bucket": row.get("bucket"),
                    "issue_type": data_status,
                    "reason": "缺少历史行情" if data_status == "NO_DATA" else "部分策略信号缺失",
                }
            )

    conclusion = pd.DataFrame(rows)
    if conclusion.empty:
        conclusion = pd.DataFrame(columns=DAILY_CONCLUSION_COLUMNS)
    else:
        for column in DAILY_CONCLUSION_COLUMNS:
            if column not in conclusion.columns:
                conclusion[column] = pd.Series(dtype="string")
        conclusion = _sort_rows(conclusion[DAILY_CONCLUSION_COLUMNS])

    data_gaps = pd.DataFrame(data_gap_rows)
    if data_gaps.empty:
        data_gaps = pd.DataFrame(columns=DATA_GAP_COLUMNS)
    else:
        for column in DATA_GAP_COLUMNS:
            if column not in data_gaps.columns:
                data_gaps[column] = pd.Series(dtype="string")
        data_gaps = _sort_rows(data_gaps[DATA_GAP_COLUMNS])
    return conclusion, long_term_evidence, short_term_evidence, data_gaps


def build_daily_conclusion_frames(
    summary: pd.DataFrame,
    eod_d: pd.DataFrame,
    eod_w: pd.DataFrame,
    eod_m: pd.DataFrame,
    intraday: pd.DataFrame,
    preclose: pd.DataFrame,
    signal_date: date,
    intraday_ts: datetime | None,
    market_data_by_symbol: dict[str, pd.DataFrame] | None = None,
    fallback_symbols: list[str] | None = None,
    runtime_config: RuntimeConfig | None = None,
) -> dict[str, pd.DataFrame]:
    conclusion, long_term_evidence, short_term_evidence, data_gaps = build_daily_conclusions(
        summary=summary,
        eod_d=eod_d,
        eod_w=eod_w,
        eod_m=eod_m,
        intraday=intraday,
        preclose=preclose,
        market_data_by_symbol=market_data_by_symbol,
        fallback_symbols=fallback_symbols,
        runtime_config=runtime_config,
    )
    hypothesis_summary = build_hypothesis_summary_frame(
        summary=conclusion,
        long_term_evidence=long_term_evidence,
        short_term_evidence=short_term_evidence,
        market_data_by_symbol=market_data_by_symbol,
    )
    operation_view = build_operation_view(conclusion)
    no_data_count = int((conclusion.get("data_status") == "NO_DATA").sum()) if not conclusion.empty else 0
    partial_count = int((conclusion.get("data_status") == "PARTIAL").sum()) if not conclusion.empty else 0
    overview = pd.DataFrame(
        [
            {"section": "report", "item": "generated_at", "value": now_shanghai().isoformat()},
            {"section": "report", "item": "signal_date", "value": signal_date.isoformat()},
            {"section": "report", "item": "intraday_ts", "value": intraday_ts.isoformat() if intraday_ts is not None else "NONE"},
            {"section": "report", "item": "symbol_count", "value": str(len(conclusion.index))},
            {"section": "report", "item": "no_data_count", "value": str(no_data_count)},
            {"section": "report", "item": "partial_count", "value": str(partial_count)},
            {"section": "legend", "item": "BUY", "value": "当前 horizon 聚合后倾向买入"},
            {"section": "legend", "item": "SELL", "value": "当前 horizon 聚合后倾向卖出"},
            {"section": "legend", "item": "HOLD", "value": "当前 horizon 聚合后倾向观望"},
            {"section": "legend", "item": "NO_DATA", "value": "标的缺少历史行情，无法形成稳定结论"},
            {"section": "legend", "item": "MISSING", "value": "本应存在的策略信号缺失，需检查上游"},
            {"section": "sheet", "item": "Operation_View", "value": "最终操作版视图：更短、更适合日常直接看"},
            {"section": "sheet", "item": "Daily_Conclusion", "value": "长线/短线简明结论主表"},
            {"section": "sheet", "item": "Hypothesis_Summary", "value": "按策略哲学分组后的聚合结论"},
            {"section": "sheet", "item": "LongTerm_Evidence", "value": "长线证据明细"},
            {"section": "sheet", "item": "ShortTerm_Evidence", "value": "短线证据明细"},
            {"section": "sheet", "item": "Data_Gaps", "value": "数据缺口与缺信号清单"},
            *_overview_count_rows(conclusion, "overall_action", "overall_action_count", ACTION_COUNT_ORDER),
            *_overview_count_rows(conclusion, "long_term_action", "long_term_action_count", ACTION_COUNT_ORDER),
            *_overview_count_rows(conclusion, "short_term_action", "short_term_action_count", ACTION_COUNT_ORDER),
            *_overview_count_rows(conclusion, "hypothesis_consensus_action", "hypothesis_consensus_count", ACTION_COUNT_ORDER),
            *_overview_count_rows(conclusion, "preclose_signal", "preclose_signal_count", PRECLOSE_COUNT_ORDER),
            {"section": "report", "item": "hypothesis_tiebreak_count", "value": str(int(conclusion.get("hypothesis_tiebreak_applied", pd.Series(dtype="bool")).fillna(False).astype(bool).sum()))},
        ]
    )
    return {
        "Operation_View": operation_view,
        "Overview": overview,
        "Daily_Conclusion": conclusion,
        "Hypothesis_Summary": hypothesis_summary,
        "LongTerm_Evidence": long_term_evidence,
        "ShortTerm_Evidence": short_term_evidence,
        "Data_Gaps": data_gaps,
    }


def load_daily_conclusion_context(
    signal_date: date | None = None,
    intraday_ts: datetime | None = None,
    intraday_bar_frequency: str = "5",
    config: PostgresConfig | None = None,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    with session_scope(config) as session:
        explicit_intraday_date = intraday_ts.date() if intraday_ts is not None else None
        reference_date = explicit_intraday_date or signal_date or latest_closed_trading_date()
        signal_dates = _resolve_eod_signal_dates(session, requested_date=reference_date)
        latest_intraday_ts = load_latest_intraday_signal_ts(session, bar_frequency=intraday_bar_frequency)
        if explicit_intraday_date is not None:
            target_date = explicit_intraday_date
            target_ts = latest_intraday_ts if latest_intraday_ts is not None and latest_intraday_ts.date() == explicit_intraday_date else None
        else:
            target_date = signal_dates["D"] or reference_date
            target_ts = latest_intraday_ts if latest_intraday_ts is not None and latest_intraday_ts.date() == target_date else None
        eod_d = load_signals_by_date(session, signal_dates["D"], mode="eod", bar_frequency="D") if signal_dates["D"] is not None else pd.DataFrame()
        eod_w = load_signals_by_date(session, signal_dates["W"], mode="eod", bar_frequency="W") if signal_dates["W"] is not None else pd.DataFrame()
        eod_m = load_signals_by_date(session, signal_dates["M"], mode="eod", bar_frequency="M") if signal_dates["M"] is not None else pd.DataFrame()
        intraday = load_intraday_signals(session, target_ts, bar_frequency=intraday_bar_frequency) if target_ts is not None else pd.DataFrame()
        report_symbols = sorted(
            set(
                symbols
                or [
                    *eod_d.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
                    *eod_w.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
                    *eod_m.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
                    *intraday.get("symbol", pd.Series(dtype="string")).astype(str).tolist(),
                ]
            )
        )
        market_data_by_symbol = load_market_prices_map(session, report_symbols, limit=240, as_of_date=target_date) if report_symbols else {}
        intraday_bars_by_symbol = (
            load_realtime_bars_map(session, symbols=report_symbols, bar_frequency=intraday_bar_frequency, limit=64)
            if report_symbols and target_ts is not None
            else {}
        )

    secondary_validation = build_secondary_validation(
        eod_d,
        market_data_by_symbol=market_data_by_symbol,
        signal_date=signal_dates["D"] or target_date,
    )
    summary = build_signal_summary(
        eod_d=eod_d,
        eod_w=eod_w,
        eod_m=eod_m,
        intraday=intraday,
        secondary_validation=secondary_validation,
    )
    preclose = build_preclose_decisions(
        summary=summary,
        market_data_by_symbol=market_data_by_symbol,
        intraday_bars_by_symbol=intraday_bars_by_symbol,
        analysis_mode="INTRADAY_PRE_CLOSE" if target_ts is not None else "POST_CLOSE",
        signal_date=target_date,
        analysis_ts=target_ts,
        fallback_symbols=report_symbols,
    )
    return {
        "signal_dates": signal_dates,
        "signal_date": target_date,
        "intraday_ts": target_ts,
        "summary": summary,
        "eod_d": eod_d,
        "eod_w": eod_w,
        "eod_m": eod_m,
        "intraday": intraday,
        "preclose": preclose,
        "market_data_by_symbol": market_data_by_symbol,
        "report_symbols": report_symbols,
    }


def _apply_action_format(workbook, worksheet, first_row: int, last_row: int, first_col: int, last_col: int) -> None:
    if last_row < first_row or last_col < first_col:
        return
    formats = {
        "BUY": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
        "SELL": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"}),
        "HOLD": workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"}),
        "NO_DATA": workbook.add_format({"bg_color": "#DDEBF7", "font_color": "#1F4E78"}),
        "MISSING": workbook.add_format({"bg_color": "#F4CCCC", "font_color": "#990000"}),
    }
    for state, cell_format in formats.items():
        worksheet.conditional_format(
            first_row,
            first_col,
            last_row,
            last_col,
            {"type": "text", "criteria": "containing", "value": state, "format": cell_format},
        )


def _set_column_widths(worksheet, frame: pd.DataFrame, max_width: int = 36) -> None:
    for index, column in enumerate(frame.columns):
        series = frame[column].astype(str) if column in frame.columns else pd.Series(dtype="string")
        content_width = int(series.map(len).max()) if not frame.empty else 0
        width = min(max(len(str(column)) + 2, content_width + 2, 12), max_width)
        worksheet.set_column(index, index, width)


def _write_daily_conclusion_workbook(output_path: Path, frames: dict[str, pd.DataFrame], engine: Literal["xlsxwriter"]) -> None:
    with pd.ExcelWriter(output_path, engine=engine) as writer:
        workbook = cast(Any, writer.book)
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = cast(Any, writer.sheets[sheet_name])
            _set_column_widths(worksheet, frame, max_width=52 if sheet_name in {"LongTerm_Evidence", "ShortTerm_Evidence"} else 36)
            worksheet.set_row(0, 22, header_format)
            if not frame.empty:
                worksheet.autofilter(0, 0, len(frame.index), len(frame.columns) - 1)
            if sheet_name in {"Daily_Conclusion", "Operation_View"}:
                worksheet.freeze_panes(1, 6)
                action_indexes = [frame.columns.get_loc(column) for column in ACTION_COLUMNS if column in frame.columns and isinstance(frame.columns.get_loc(column), int)]
                for column_index in action_indexes:
                    if isinstance(column_index, int):
                        _apply_action_format(workbook, worksheet, 1, len(frame.index), column_index, column_index)
            else:
                worksheet.freeze_panes(1, 1)
            if sheet_name == "Operation_View":
                worksheet.activate()
                worksheet.set_first_sheet()


def export_daily_conclusion_artifacts(
    frames: dict[str, pd.DataFrame],
    signal_date: date,
    intraday_ts: datetime | None,
    output_dir: str | Path = "reports/daily_conclusion",
) -> dict[str, Path]:
    engine = _resolve_excel_engine()
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = intraday_ts.strftime("%Y%m%d_%H%M") if intraday_ts is not None else signal_date.strftime("%Y%m%d")
    csv_path = folder / f"daily_conclusion_{suffix}.csv"
    operation_csv_path = folder / f"daily_conclusion_operation_{suffix}.csv"
    json_path = folder / f"daily_conclusion_{suffix}.json"
    xlsx_path = folder / f"daily_conclusion_{suffix}.xlsx"

    daily_conclusion = frames["Daily_Conclusion"]
    operation_view = frames["Operation_View"]
    daily_conclusion.to_csv(csv_path, index=False, encoding="utf-8-sig")
    operation_view.to_csv(operation_csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(
            {
                "signal_date": signal_date.isoformat(),
                "intraday_ts": intraday_ts.isoformat() if intraday_ts is not None else None,
                "rows": int(len(daily_conclusion.index)),
                "operation_rows": int(len(operation_view.index)),
                "operation_view": operation_view.to_dict(orient="records"),
                "records": daily_conclusion.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        _write_daily_conclusion_workbook(output_path=xlsx_path, frames=frames, engine=engine)
    except PermissionError:
        fallback_suffix = now_shanghai().strftime("%Y%m%d_%H%M%S")
        xlsx_path = folder / f"daily_conclusion_{suffix}_{fallback_suffix}.xlsx"
        _write_daily_conclusion_workbook(output_path=xlsx_path, frames=frames, engine=engine)

    return {"csv_path": csv_path, "operation_csv_path": operation_csv_path, "json_path": json_path, "xlsx_path": xlsx_path}


def export_daily_conclusion_report(
    signal_date: date | None = None,
    intraday_ts: datetime | None = None,
    intraday_bar_frequency: str = "5",
    output_dir: str | Path = "reports/daily_conclusion",
    config: PostgresConfig | None = None,
) -> dict[str, object]:
    universe = load_universe_config()
    universe_symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    context = load_daily_conclusion_context(
        signal_date=signal_date,
        intraday_ts=intraday_ts,
        intraday_bar_frequency=intraday_bar_frequency,
        config=config,
        symbols=universe_symbols,
    )
    frames = build_daily_conclusion_frames(
        summary=cast(pd.DataFrame, context["summary"]),
        eod_d=cast(pd.DataFrame, context["eod_d"]),
        eod_w=cast(pd.DataFrame, context["eod_w"]),
        eod_m=cast(pd.DataFrame, context["eod_m"]),
        intraday=cast(pd.DataFrame, context["intraday"]),
        preclose=cast(pd.DataFrame, context["preclose"]),
        signal_date=cast(date, context["signal_date"]),
        intraday_ts=cast(datetime | None, context["intraday_ts"]),
        market_data_by_symbol=cast(dict[str, pd.DataFrame], context["market_data_by_symbol"]),
        fallback_symbols=cast(list[str], context["report_symbols"]),
    )
    target_date = cast(date, context["signal_date"])
    target_ts = cast(datetime | None, context["intraday_ts"])
    signal_dates = cast(dict[str, date | None], context["signal_dates"])
    exports = export_daily_conclusion_artifacts(frames=frames, signal_date=target_date, intraday_ts=target_ts, output_dir=output_dir)
    daily_conclusion = frames["Daily_Conclusion"]
    return {
        "signal_date": target_date.isoformat(),
        "signal_date_d": signal_dates["D"].isoformat() if signal_dates["D"] is not None else None,
        "signal_date_w": signal_dates["W"].isoformat() if signal_dates["W"] is not None else None,
        "signal_date_m": signal_dates["M"].isoformat() if signal_dates["M"] is not None else None,
        "intraday_ts": target_ts.isoformat() if target_ts is not None else None,
        "rows": int(len(daily_conclusion.index)),
        "operation_rows": int(len(frames["Operation_View"].index)),
        "no_data_count": int((daily_conclusion.get("data_status") == "NO_DATA").sum()) if not daily_conclusion.empty else 0,
        "partial_count": int((daily_conclusion.get("data_status") == "PARTIAL").sum()) if not daily_conclusion.empty else 0,
        "sheet_names": list(frames.keys()),
        "csv_path": str(exports["csv_path"]),
        "operation_csv_path": str(exports["operation_csv_path"]),
        "json_path": str(exports["json_path"]),
        "xlsx_path": str(exports["xlsx_path"]),
    }
