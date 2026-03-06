from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config.settings import PostgresConfig, load_symbol_meta_map
from core.trading_calendar import latest_closed_trading_date
from data_storage.database import session_scope
from data_storage.realtime_repository import load_intraday_signals, load_latest_intraday_signal_ts
from data_storage.repository import load_latest_signal_date, load_market_prices_map, load_signals_by_date
from signal_service.secondary_validation import build_secondary_validation
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names

EOD_WEIGHTS = {"eod_d": 1.0, "eod_w": 2.0, "eod_m": 3.0}
INTRADAY_WEIGHT = 1.5
ALIGNMENT_BONUS = {"ALIGNED": 2.0, "DIVERGED": -2.0, "NEUTRAL": 0.0, "NO_INTRADAY": 0.0}
SECTOR_KEYWORDS = {"银行", "券商", "有色", "通信", "电力"}
THEME_KEYWORDS = {"人工智能", "金融科技", "科技", "AH股", "科创"}
SECONDARY_ACTION_WEIGHTS = {"BUY_CONFIRM": 2.0, "SELL_CONFIRM": -2.0, "BUY_FILTERED": -1.0, "HOLD_OBSERVE": 0.0}
REVIEW_GATE_BONUS = {"CONFIRM": 1.0, "CAUTION": -0.75, "REJECT": -1.5, "INSUFFICIENT_DATA": 0.0}
PUSH_TOP_N = 3
PUSH_ACTION_PRIORITY = {"PRIORITY_BUY": 2.0, "PRIORITY_SELL": 2.0, "TREND_BUY": 1.2, "TREND_SELL": 1.2, "WATCHLIST": 0.5}


def _normalize_signal(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"BUY", "SELL", "HOLD"}:
        return text
    return "HOLD"


def _signal_to_score(value: object) -> float:
    signal = _normalize_signal(value)
    if signal == "BUY":
        return 1.0
    if signal == "SELL":
        return -1.0
    return 0.0


def _coerce_float(value: object, default: float) -> float:
    converted = pd.to_numeric([value], errors="coerce")[0]
    if pd.isna(converted):
        return float(default)
    return float(converted)


def _classify_asset_type(display_symbol: object) -> str:
    text = str(display_symbol)
    if text.startswith("E"):
        return "ETF"
    return "INDEX"


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


def _dominant_signal(series: pd.Series) -> str:
    values = [_normalize_signal(value) for value in series.tolist()]
    counts = {"BUY": values.count("BUY"), "SELL": values.count("SELL"), "HOLD": values.count("HOLD")}
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return "MIXED"
    return ordered[0][0]


def _summarize_by_symbol(frame: pd.DataFrame, column_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["symbol", column_name])
    table = frame.copy()
    table["symbol"] = table["symbol"].astype(str)
    table["signal"] = table["signal"].map(_normalize_signal)
    rows = []
    for symbol, subset in table.groupby("symbol", dropna=False):
        rows.append({"symbol": str(symbol), column_name: _dominant_signal(subset["signal"])})
    return pd.DataFrame(rows)


def _compute_eod_bias(row: pd.Series) -> str:
    values = [row.get("eod_d"), row.get("eod_w"), row.get("eod_m")]
    normalized = [_normalize_signal(value) for value in values if value is not None and str(value) != "nan"]
    if not normalized:
        return "HOLD"
    buy = normalized.count("BUY")
    sell = normalized.count("SELL")
    hold = normalized.count("HOLD")
    if buy > sell and buy >= hold:
        return "BUY"
    if sell > buy and sell >= hold:
        return "SELL"
    if hold > buy and hold > sell:
        return "HOLD"
    return "MIXED"


def _compute_alignment(row: pd.Series) -> str:
    eod_bias = str(row.get("eod_bias", "HOLD"))
    intraday = str(row.get("intraday", "HOLD"))
    if intraday in {"", "nan", "None"}:
        return "NO_INTRADAY"
    if eod_bias == intraday and eod_bias in {"BUY", "SELL"}:
        return "ALIGNED"
    if eod_bias in {"BUY", "SELL"} and intraday in {"BUY", "SELL"} and eod_bias != intraday:
        return "DIVERGED"
    return "NEUTRAL"


def _compute_eod_score(row: pd.Series) -> float:
    total = 0.0
    for column, weight in EOD_WEIGHTS.items():
        total += _signal_to_score(row.get(column)) * weight
    return float(total)


def _compute_intraday_score(row: pd.Series) -> float:
    return float(_signal_to_score(row.get("intraday")) * INTRADAY_WEIGHT)


def _compute_secondary_score(row: pd.Series) -> float:
    action = str(row.get("secondary_action", "HOLD_OBSERVE"))
    confidence = float(row.get("secondary_confidence", 50.0))
    weight = SECONDARY_ACTION_WEIGHTS.get(action, 0.0)
    return float(weight * max(0.0, min(confidence, 100.0)) / 100.0)


def _compute_composite_score(row: pd.Series) -> float:
    eod_score = float(row.get("eod_score", 0.0))
    intraday_score = float(row.get("intraday_score", 0.0))
    secondary_score = float(row.get("secondary_score", 0.0))
    bonus = ALIGNMENT_BONUS.get(str(row.get("alignment", "NEUTRAL")), 0.0)
    gate_bonus = REVIEW_GATE_BONUS.get(str(row.get("review_gate", "INSUFFICIENT_DATA")), 0.0)
    return float(eod_score + intraday_score + secondary_score + bonus + gate_bonus)


def _compute_dashboard_action(row: pd.Series) -> str:
    composite = float(row.get("composite_score", 0.0))
    alignment = str(row.get("alignment", "NEUTRAL"))
    eod_bias = str(row.get("eod_bias", "HOLD"))
    if composite >= 4.0 and alignment == "ALIGNED" and eod_bias == "BUY":
        return "PRIORITY_BUY"
    if composite <= -4.0 and alignment == "ALIGNED" and eod_bias == "SELL":
        return "PRIORITY_SELL"
    if alignment == "DIVERGED":
        return "WATCHLIST"
    if eod_bias in {"BUY", "SELL"}:
        return f"TREND_{eod_bias}"
    return "NEUTRAL"


def _apply_ranking(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        summary["eod_score"] = pd.Series(dtype="float64")
        summary["intraday_score"] = pd.Series(dtype="float64")
        summary["secondary_score"] = pd.Series(dtype="float64")
        summary["composite_score"] = pd.Series(dtype="float64")
        summary["dashboard_action"] = pd.Series(dtype="string")
        summary["conviction_rank"] = pd.Series(dtype="int64")
        return summary

    table = summary.copy()
    table["eod_score"] = table.apply(_compute_eod_score, axis=1)
    table["intraday_score"] = table.apply(_compute_intraday_score, axis=1)
    table["secondary_score"] = table.apply(_compute_secondary_score, axis=1)
    table["composite_score"] = table.apply(_compute_composite_score, axis=1)
    table["dashboard_action"] = table.apply(_compute_dashboard_action, axis=1)
    table["abs_composite_score"] = table["composite_score"].abs()
    table = table.sort_values(["abs_composite_score", "composite_score", "symbol"], ascending=[False, False, True]).reset_index(drop=True)
    table["conviction_rank"] = table.index + 1
    return table.drop(columns=["abs_composite_score"])


def _enrich_dashboard_labels(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        summary["asset_type"] = pd.Series(dtype="string")
        summary["bucket"] = pd.Series(dtype="string")
        return summary

    table = summary.copy()
    meta_map = load_symbol_meta_map()
    if "name" not in table.columns or "display_symbol" not in table.columns:
        table = enrich_signal_frame_with_symbol_names(table, symbol_meta_map=meta_map)
    table["asset_type"] = table["display_symbol"].map(_classify_asset_type)
    table["bucket"] = table.apply(lambda row: _classify_bucket(row.get("name"), row.get("asset_type")), axis=1)
    return table


def _secondary_review_frame(secondary_validation: dict[str, object] | None) -> pd.DataFrame:
    if not secondary_validation:
        return pd.DataFrame(columns=["symbol", "secondary_action", "secondary_confidence", "primary_action", "review_score", "review_gate"])

    reviews = secondary_validation.get("symbol_reviews", [])
    if not isinstance(reviews, list) or not reviews:
        return pd.DataFrame(columns=["symbol", "secondary_action", "secondary_confidence", "primary_action", "review_score", "review_gate"])

    review_score = secondary_validation.get("review_score")
    review_gate = secondary_validation.get("review_gate")
    rows: list[dict[str, object]] = []
    for review in reviews:
        if not isinstance(review, dict):
            continue
        rows.append(
            {
                "symbol": str(review.get("symbol", "")),
                "primary_action": str(review.get("primary_action", "HOLD")),
                "secondary_action": str(review.get("secondary_action", "HOLD_OBSERVE")),
                "secondary_confidence": _coerce_float(review.get("confidence", 50.0), default=50.0),
                "review_score": _coerce_float(review_score, default=50.0),
                "review_gate": str(review_gate or "INSUFFICIENT_DATA"),
            }
        )
    return pd.DataFrame(rows)


def build_group_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=["bucket", "asset_type", "count", "avg_composite_score", "avg_secondary_confidence", "aligned_count", "priority_buy_count", "priority_sell_count", "top_symbol"])

    table = summary.copy()
    rows: list[dict[str, object]] = []
    grouped = table.groupby(["bucket", "asset_type"], dropna=False)
    for (bucket, asset_type), subset in grouped:
        ordered = subset.sort_values(["composite_score", "conviction_rank"], ascending=[False, True])
        rows.append(
            {
                "bucket": str(bucket),
                "asset_type": str(asset_type),
                "count": int(len(subset.index)),
                "avg_composite_score": round(float(subset["composite_score"].mean()), 4),
                "avg_secondary_confidence": round(float(pd.to_numeric(subset.get("secondary_confidence", pd.Series(dtype="float64")), errors="coerce").fillna(0.0).mean()), 4),
                "aligned_count": int((subset["alignment"] == "ALIGNED").sum()),
                "priority_buy_count": int((subset["dashboard_action"] == "PRIORITY_BUY").sum()),
                "priority_sell_count": int((subset["dashboard_action"] == "PRIORITY_SELL").sum()),
                "top_symbol": str(ordered.iloc[0]["symbol"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["avg_composite_score", "count", "bucket"], ascending=[False, False, True]).reset_index(drop=True)


def build_top_candidates(summary: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=["direction", "conviction_rank", "symbol", "display_symbol", "name", "bucket", "composite_score", "dashboard_action", "alignment", "eod_bias", "intraday", "secondary_action", "secondary_confidence", "review_gate"])

    table = summary.copy()
    buy_mask = table["dashboard_action"].isin(["PRIORITY_BUY", "TREND_BUY"])
    sell_mask = table["dashboard_action"].isin(["PRIORITY_SELL", "TREND_SELL"])
    top_buy = table.loc[buy_mask].sort_values(["composite_score", "conviction_rank"], ascending=[False, True]).head(limit).copy()
    top_sell = table.loc[sell_mask].sort_values(["composite_score", "conviction_rank"], ascending=[True, True]).head(limit).copy()
    top_buy["direction"] = "BUY"
    top_sell["direction"] = "SELL"
    columns = ["direction", "conviction_rank", "symbol", "display_symbol", "name", "bucket", "composite_score", "dashboard_action", "alignment", "eod_bias", "intraday", "secondary_action", "secondary_confidence", "review_gate"]
    combined = pd.concat([top_buy[columns], top_sell[columns]], ignore_index=True) if not top_buy.empty or not top_sell.empty else pd.DataFrame(columns=columns)
    return combined.reset_index(drop=True)


def _build_empty_push_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "push_rank",
            "symbol",
            "display_symbol",
            "name",
            "bucket",
            "dashboard_action",
            "previous_dashboard_action",
            "composite_score",
            "previous_composite_score",
            "score_delta",
            "change_score",
            "change_reason",
            "secondary_action",
            "secondary_confidence",
            "review_gate",
        ]
    )


def build_push_candidates(current_summary: pd.DataFrame, previous_summary: pd.DataFrame | None = None, limit: int = PUSH_TOP_N) -> pd.DataFrame:
    if current_summary.empty:
        return _build_empty_push_candidates()

    table = current_summary.copy()
    previous = previous_summary.copy() if previous_summary is not None and not previous_summary.empty else pd.DataFrame(columns=["symbol"])

    if not previous.empty:
        previous = previous.rename(
            columns={
                "dashboard_action": "previous_dashboard_action",
                "composite_score": "previous_composite_score",
                "conviction_rank": "previous_conviction_rank",
                "review_gate": "previous_review_gate",
                "secondary_action": "previous_secondary_action",
            }
        )
        keep_columns = [
            column
            for column in [
                "symbol",
                "previous_dashboard_action",
                "previous_composite_score",
                "previous_conviction_rank",
                "previous_review_gate",
                "previous_secondary_action",
            ]
            if column in previous.columns
        ]
        previous = previous[keep_columns]
        table = table.merge(previous, on="symbol", how="left")
    else:
        table["previous_dashboard_action"] = pd.Series(dtype="string")
        table["previous_composite_score"] = pd.Series(dtype="float64")
        table["previous_conviction_rank"] = pd.Series(dtype="float64")
        table["previous_review_gate"] = pd.Series(dtype="string")
        table["previous_secondary_action"] = pd.Series(dtype="string")

    table["candidate_active"] = table["dashboard_action"].isin(["PRIORITY_BUY", "PRIORITY_SELL", "TREND_BUY", "TREND_SELL", "WATCHLIST"])
    table["is_new_symbol"] = table["previous_dashboard_action"].isna()
    table["action_changed"] = table["dashboard_action"] != table["previous_dashboard_action"].fillna("")
    table["gate_changed"] = table["review_gate"] != table["previous_review_gate"].fillna("")
    previous_score = pd.to_numeric(table["previous_composite_score"], errors="coerce")
    current_score = pd.to_numeric(table["composite_score"], errors="coerce")
    table["score_delta"] = (current_score - previous_score).abs().fillna(current_score.abs())
    previous_rank = pd.to_numeric(table["previous_conviction_rank"], errors="coerce")
    current_rank = pd.to_numeric(table["conviction_rank"], errors="coerce")
    table["rank_improved"] = (previous_rank - current_rank).fillna(0.0)

    def _reason(row: pd.Series) -> str:
        if bool(row.get("is_new_symbol", False)):
            return "NEW_ENTRY"
        if bool(row.get("action_changed", False)):
            return "ACTION_CHANGED"
        if bool(row.get("gate_changed", False)):
            return "REVIEW_GATE_CHANGED"
        if float(row.get("score_delta", 0.0)) >= 1.5:
            return "SCORE_SHIFT"
        if float(row.get("rank_improved", 0.0)) > 0:
            return "RANK_UP"
        return "MINOR"

    table["change_reason"] = table.apply(_reason, axis=1)
    table["change_score"] = (
        table["score_delta"]
        + table["is_new_symbol"].astype(int) * 2.0
        + table["action_changed"].astype(int) * 2.0
        + table["gate_changed"].astype(int) * 1.0
        + table["rank_improved"].clip(lower=0.0) * 0.25
        + table["dashboard_action"].map(PUSH_ACTION_PRIORITY).fillna(0.0)
    )

    interesting = table[
        table["candidate_active"]
        & (
            table["is_new_symbol"]
            | table["action_changed"]
            | table["gate_changed"]
            | (table["score_delta"] >= 1.0)
            | (table["rank_improved"] > 0)
        )
    ].copy()

    if interesting.empty:
        interesting = table.loc[table["candidate_active"]].copy()
        if interesting.empty:
            return _build_empty_push_candidates()
        interesting["change_reason"] = "SNAPSHOT"
        interesting["change_score"] = pd.to_numeric(interesting["composite_score"], errors="coerce").abs().fillna(0.0)

    interesting = interesting.sort_values(
        ["change_score", "composite_score", "conviction_rank", "symbol"],
        ascending=[False, False, True, True],
    ).head(max(1, limit)).reset_index(drop=True)
    interesting["push_rank"] = interesting.index + 1

    columns = [
        "push_rank",
        "symbol",
        "display_symbol",
        "name",
        "bucket",
        "dashboard_action",
        "previous_dashboard_action",
        "composite_score",
        "previous_composite_score",
        "score_delta",
        "change_score",
        "change_reason",
        "secondary_action",
        "secondary_confidence",
        "review_gate",
    ]
    for column in columns:
        if column not in interesting.columns:
            interesting[column] = pd.Series(dtype="string")
    return interesting[columns]


def resolve_summary_artifact_paths(summary_path: str | Path) -> dict[str, Path]:
    path = Path(summary_path)
    stem = path.stem
    suffix = stem.replace("signal_summary_", "", 1)
    folder = path.parent
    return {
        "summary_path": path,
        "group_summary_path": folder / f"signal_group_summary_{suffix}.csv",
        "top_candidates_path": folder / f"signal_top_candidates_{suffix}.csv",
        "push_candidates_path": folder / f"signal_push_candidates_{suffix}.csv",
    }


def _load_previous_summary(output_path: Path) -> pd.DataFrame:
    folder = output_path.parent
    candidates = sorted(folder.glob("signal_summary_*.csv"))
    previous = [item for item in candidates if item.name != output_path.name]
    if not previous:
        return pd.DataFrame()
    latest = previous[-1]
    return pd.read_csv(latest)


def build_signal_summary(
    eod_d: pd.DataFrame,
    eod_w: pd.DataFrame,
    eod_m: pd.DataFrame,
    intraday: pd.DataFrame,
    secondary_validation: dict[str, object] | None = None,
) -> pd.DataFrame:
    frames = [
        _summarize_by_symbol(eod_d, "eod_d"),
        _summarize_by_symbol(eod_w, "eod_w"),
        _summarize_by_symbol(eod_m, "eod_m"),
        _summarize_by_symbol(intraday.rename(columns={"ts": "date"}) if not intraday.empty else intraday, "intraday"),
    ]

    summary = pd.DataFrame(columns=["symbol"])
    for frame in frames:
        if frame.empty:
            continue
        summary = frame if summary.empty else summary.merge(frame, on="symbol", how="outer")

    if summary.empty:
        summary = pd.DataFrame(
            columns=[
                "symbol",
                "eod_d",
                "eod_w",
                "eod_m",
                "intraday",
                "eod_bias",
                "alignment",
                "eod_score",
                "intraday_score",
                "secondary_score",
                "composite_score",
                "dashboard_action",
                "conviction_rank",
            ]
        )
    else:
        for column in ["eod_d", "eod_w", "eod_m", "intraday"]:
            if column not in summary.columns:
                summary[column] = pd.Series(dtype="string")
        secondary_frame = _secondary_review_frame(secondary_validation)
        if not secondary_frame.empty:
            summary = summary.merge(secondary_frame, on="symbol", how="left")
        else:
            summary["primary_action"] = pd.Series(dtype="string")
            summary["secondary_action"] = pd.Series(dtype="string")
            summary["secondary_confidence"] = pd.Series(dtype="float64")
            summary["review_score"] = pd.Series(dtype="float64")
            summary["review_gate"] = pd.Series(dtype="string")
        summary["eod_bias"] = summary.apply(_compute_eod_bias, axis=1)
        summary["alignment"] = summary.apply(_compute_alignment, axis=1)
        summary["secondary_confidence"] = pd.to_numeric(summary["secondary_confidence"], errors="coerce").fillna(50.0)
        summary["review_score"] = pd.to_numeric(summary["review_score"], errors="coerce").fillna(50.0)
        summary["review_gate"] = summary["review_gate"].fillna("INSUFFICIENT_DATA")
        summary["secondary_action"] = summary["secondary_action"].fillna("HOLD_OBSERVE")
        summary = _apply_ranking(summary)
    summary = enrich_signal_frame_with_symbol_names(summary)
    summary = _enrich_dashboard_labels(summary)
    preferred_order = [
        "conviction_rank",
        "symbol",
        "display_symbol",
        "name",
        "asset_type",
        "bucket",
        "eod_d",
        "eod_w",
        "eod_m",
        "intraday",
        "eod_bias",
        "alignment",
        "primary_action",
        "secondary_action",
        "secondary_confidence",
        "review_gate",
        "review_score",
        "eod_score",
        "intraday_score",
        "secondary_score",
        "composite_score",
        "dashboard_action",
    ]
    existing = [column for column in preferred_order if column in summary.columns]
    remaining = [column for column in summary.columns if column not in existing]
    return summary[existing + remaining].reset_index(drop=True)


def export_signal_summary(
    signal_date: date | None = None,
    intraday_ts: datetime | None = None,
    intraday_bar_frequency: str = "5",
    output_dir: str | Path = "reports/summary",
    config: PostgresConfig | None = None,
) -> Path:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    with session_scope(config) as session:
        target_date = signal_date or load_latest_signal_date(session, mode="eod", bar_frequency="D") or latest_closed_trading_date()
        target_ts = intraday_ts or load_latest_intraday_signal_ts(session, bar_frequency=intraday_bar_frequency)
        eod_d = load_signals_by_date(session, target_date, mode="eod", bar_frequency="D")
        eod_w = load_signals_by_date(session, target_date, mode="eod", bar_frequency="W")
        eod_m = load_signals_by_date(session, target_date, mode="eod", bar_frequency="M")
        intraday = load_intraday_signals(session, target_ts, bar_frequency=intraday_bar_frequency) if target_ts is not None else pd.DataFrame()
        symbols = sorted(eod_d["symbol"].astype(str).unique().tolist()) if not eod_d.empty else []
        market_data_by_symbol = load_market_prices_map(session, symbols, limit=240, as_of_date=target_date) if symbols else {}

    secondary_validation = build_secondary_validation(eod_d, market_data_by_symbol=market_data_by_symbol, signal_date=target_date)
    summary = build_signal_summary(
        eod_d=eod_d,
        eod_w=eod_w,
        eod_m=eod_m,
        intraday=intraday,
        secondary_validation=secondary_validation,
    )
    suffix = target_ts.strftime("%Y%m%d_%H%M") if target_ts is not None else target_date.strftime("%Y%m%d")
    output_path = folder / f"signal_summary_{suffix}.csv"
    previous_summary = _load_previous_summary(output_path)
    summary.to_csv(output_path, index=False, encoding="utf-8-sig")

    artifact_paths = resolve_summary_artifact_paths(output_path)
    build_group_summary(summary).to_csv(artifact_paths["group_summary_path"], index=False, encoding="utf-8-sig")

    build_top_candidates(summary).to_csv(artifact_paths["top_candidates_path"], index=False, encoding="utf-8-sig")
    build_push_candidates(summary, previous_summary=previous_summary, limit=PUSH_TOP_N).to_csv(
        artifact_paths["push_candidates_path"],
        index=False,
        encoding="utf-8-sig",
    )
    return output_path
