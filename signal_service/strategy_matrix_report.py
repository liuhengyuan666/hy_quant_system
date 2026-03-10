from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, cast

import pandas as pd

from config.settings import PostgresConfig, load_universe_config
from core.clock import now_shanghai
from core.trading_calendar import latest_closed_trading_date
from data_storage.database import session_scope
from data_storage.realtime_repository import load_intraday_signals, load_latest_intraday_signal_ts
from data_storage.repository import load_latest_signal_date, load_latest_signal_date_on_or_before, load_market_prices_map, load_signals_by_date
from signal_service.preclose_decision import build_preclose_decisions
from signal_service.secondary_validation import build_secondary_validation
from signal_service.summary_view import build_signal_summary
from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names
from strategy_engine.library import MARKET_HYPOTHESIS_ORDER, build_strategy_specs, list_strategy_names, market_hypothesis_label

MATRIX_META_COLUMNS = ["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket"]
ACTION_FOCUS_COLUMNS = [
    "conviction_rank",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "dashboard_action",
    "eod_d_active",
    "eod_w_active",
    "eod_m_active",
    "intraday_active",
    "active_mode_count",
    "preclose_signal",
    "preclose_score",
]
SUMMARY_SHEET_COLUMNS = [
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
    "secondary_action",
    "secondary_confidence",
    "review_gate",
    "review_score",
    "composite_score",
    "dashboard_action",
]
PRE_CLOSE_SHEET_COLUMNS = [
    "conviction_rank",
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
    "day_change_pct",
    "distance_to_ma20_pct",
    "eod_bias",
    "alignment",
    "secondary_action",
    "secondary_confidence",
    "review_gate",
    "dashboard_action",
]
SIGNAL_STATES = ("BUY", "SELL", "HOLD", "NOT_RUN", "N/A", "NO_DATA", "MISSING")
ASSET_TYPE_ORDER = {"INDEX": 0, "ETF": 1}
SECTOR_KEYWORDS = {"银行", "券商", "有色", "通信", "电力"}
THEME_KEYWORDS = {"人工智能", "金融科技", "科技", "AH股", "科创"}


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


def _resolve_excel_engine() -> Literal["xlsxwriter"]:
    if importlib.util.find_spec("xlsxwriter") is not None:
        return "xlsxwriter"
    raise ImportError("xlsxwriter is required for strategy matrix Excel export. Install dependencies from requirements.txt")


def _empty_base_rows() -> pd.DataFrame:
    return pd.DataFrame(columns=MATRIX_META_COLUMNS)


def _build_fallback_rows(symbols: list[str], start_rank: int = 1) -> pd.DataFrame:
    if not symbols:
        return _empty_base_rows()
    rows = pd.DataFrame({"symbol": symbols})
    rows = enrich_signal_frame_with_symbol_names(rows)
    rows["asset_type"] = rows["display_symbol"].map(_classify_asset_type)
    rows["bucket"] = rows.apply(lambda row: _classify_bucket(row.get("name"), row.get("asset_type")), axis=1)
    rows["conviction_rank"] = pd.RangeIndex(start=start_rank, stop=start_rank + len(rows.index))
    return rows[MATRIX_META_COLUMNS]


def _sort_report_rows(frame: pd.DataFrame) -> pd.DataFrame:
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


def _build_base_rows(
    summary: pd.DataFrame,
    fallback_signals: Iterable[pd.DataFrame] = (),
    fallback_symbols: list[str] | None = None,
) -> pd.DataFrame:
    if not summary.empty:
        table = summary.copy()
        for column in MATRIX_META_COLUMNS:
            if column not in table.columns:
                table[column] = pd.Series(dtype="string")
        missing_symbols = sorted(set(fallback_symbols or []) - set(table["symbol"].astype(str).tolist()))
        if missing_symbols:
            existing_ranks = pd.to_numeric(table["conviction_rank"], errors="coerce")
            next_rank = int(existing_ranks.max()) + 1 if not existing_ranks.dropna().empty else 1
            table = pd.concat([table[MATRIX_META_COLUMNS], _build_fallback_rows(missing_symbols, start_rank=next_rank)], ignore_index=True)
        return _sort_report_rows(table[MATRIX_META_COLUMNS])

    signal_frames = [frame for frame in fallback_signals if not frame.empty and "symbol" in frame.columns]
    if not signal_frames and not fallback_symbols:
        return _empty_base_rows()

    symbols = sorted({str(symbol) for frame in signal_frames for symbol in frame["symbol"].astype(str).tolist()} | set(fallback_symbols or []))
    return _sort_report_rows(_build_fallback_rows(symbols, start_rank=1))


def _complete_summary_frame(
    summary: pd.DataFrame,
    fallback_symbols: list[str] | None,
    no_data_symbols: set[str],
    has_intraday: bool,
) -> pd.DataFrame:
    base_rows = _build_base_rows(summary, fallback_symbols=fallback_symbols)
    if base_rows.empty:
        return pd.DataFrame(columns=SUMMARY_SHEET_COLUMNS)
    extra_columns = [column for column in summary.columns if column not in MATRIX_META_COLUMNS] if not summary.empty else []
    details = summary[["symbol", *extra_columns]].copy() if extra_columns else pd.DataFrame(columns=["symbol"])
    table = base_rows.merge(details, on="symbol", how="left") if not details.empty else base_rows.copy()
    signal_defaults = {
        "eod_d": "MISSING",
        "eod_w": "MISSING",
        "eod_m": "MISSING",
        "intraday": "NOT_RUN" if has_intraday else "NOT_RUN",
    }
    neutral_defaults: dict[str, str | float] = {
        "eod_bias": "HOLD",
        "alignment": "NEUTRAL",
        "secondary_action": "HOLD_OBSERVE",
        "secondary_confidence": 50.0,
        "review_gate": "INSUFFICIENT_DATA",
        "review_score": 50.0,
        "composite_score": 0.0,
        "dashboard_action": "NEUTRAL",
    }
    for column, default in signal_defaults.items():
        if column not in table.columns:
            table[column] = default
        else:
            table[column] = table[column].fillna(default)
    if no_data_symbols:
        no_data_mask = table["symbol"].astype(str).isin(no_data_symbols)
        for column in signal_defaults:
            table.loc[no_data_mask, column] = "NO_DATA"
    for column, default in neutral_defaults.items():
        if column not in table.columns:
            table[column] = default
        elif isinstance(default, str):
            table[column] = table[column].fillna(default)
        else:
            table[column] = pd.to_numeric(table[column], errors="coerce").fillna(float(default))
    return _sort_report_rows(table)


def _signal_lookup(frame: pd.DataFrame) -> dict[tuple[str, str], str]:
    if frame.empty:
        return {}
    table = frame.copy()
    if "symbol" not in table.columns or "strategy" not in table.columns or "signal" not in table.columns:
        return {}
    table["symbol"] = table["symbol"].astype(str)
    table["strategy"] = table["strategy"].astype(str)
    table["signal"] = table["signal"].astype(str).str.upper()
    lookup: dict[tuple[str, str], str] = {}
    for _, row in table.iterrows():
        lookup[(str(row["symbol"]), str(row["strategy"]))] = str(row["signal"])
    return lookup


def build_strategy_signal_matrix(
    summary: pd.DataFrame,
    signals_frame: pd.DataFrame,
    supported_mode: str,
    no_data_symbols: set[str] | None = None,
    fallback_symbols: list[str] | None = None,
) -> pd.DataFrame:
    strategy_specs = build_strategy_specs()
    strategy_order = [item.name for item in strategy_specs]
    spec_by_name = {item.name: item for item in strategy_specs}
    lookup = _signal_lookup(signals_frame)
    base_rows = _build_base_rows(summary, fallback_signals=(signals_frame,), fallback_symbols=fallback_symbols)
    if base_rows.empty:
        return pd.DataFrame(columns=MATRIX_META_COLUMNS + strategy_order)

    matrix = base_rows.copy()
    missing_market_data = no_data_symbols or set()
    for strategy_name in strategy_order:
        spec = spec_by_name[strategy_name]
        values: list[str] = []
        for _, row in matrix.iterrows():
            symbol = str(row.get("symbol", ""))
            asset_type = str(row.get("asset_type", "INDEX"))
            if supported_mode not in spec.supported_modes:
                values.append("NOT_RUN")
                continue
            if spec.universe == "etf" and asset_type != "ETF":
                values.append("N/A")
                continue
            if symbol in missing_market_data:
                values.append("NO_DATA")
                continue
            signal = lookup.get((symbol, strategy_name))
            values.append(signal if signal in {"BUY", "SELL", "HOLD"} else "MISSING")
        matrix[strategy_name] = values
    return matrix


def build_strategy_statistics(matrix_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for sheet_name, frame in matrix_frames.items():
        strategy_columns = [name for name in list_strategy_names() if name in frame.columns]
        for strategy_name in strategy_columns:
            counts = frame[strategy_name].astype(str).value_counts().to_dict()
            applicable = int(len(frame.index) - counts.get("NOT_RUN", 0) - counts.get("N/A", 0))
            rows.append(
                {
                    "sheet": sheet_name,
                    "strategy": strategy_name,
                    "buy_count": int(counts.get("BUY", 0)),
                    "sell_count": int(counts.get("SELL", 0)),
                    "hold_count": int(counts.get("HOLD", 0)),
                    "not_run_count": int(counts.get("NOT_RUN", 0)),
                    "na_count": int(counts.get("N/A", 0)),
                    "no_data_count": int(counts.get("NO_DATA", 0)),
                    "missing_count": int(counts.get("MISSING", 0)),
                    "applicable_rows": int(applicable - counts.get("NO_DATA", 0)),
                    "active_signal_count": int(counts.get("BUY", 0) + counts.get("SELL", 0)),
                }
            )
    return pd.DataFrame(rows)


def build_hypothesis_statistics(matrix_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    specs = build_strategy_specs()
    strategies_by_hypothesis: dict[str, list[str]] = {}
    for spec in specs:
        strategies_by_hypothesis.setdefault(spec.market_hypothesis, []).append(spec.name)

    rows: list[dict[str, object]] = []
    states = ["BUY", "SELL", "HOLD", "NOT_RUN", "N/A", "NO_DATA", "MISSING"]
    for sheet_name, frame in matrix_frames.items():
        for market_hypothesis in MARKET_HYPOTHESIS_ORDER:
            strategy_columns = [name for name in strategies_by_hypothesis.get(market_hypothesis, []) if name in frame.columns]
            if not strategy_columns:
                continue

            counts = {state: 0 for state in states}
            for strategy_name in strategy_columns:
                strategy_counts = frame[strategy_name].astype(str).value_counts().to_dict()
                for state in states:
                    counts[state] += int(strategy_counts.get(state, 0))

            applicable = len(frame.index) * len(strategy_columns) - counts["NOT_RUN"] - counts["N/A"]
            rows.append(
                {
                    "sheet": sheet_name,
                    "market_hypothesis": market_hypothesis,
                    "market_hypothesis_label": market_hypothesis_label(market_hypothesis),
                    "strategy_count": int(len(strategy_columns)),
                    "buy_count": counts["BUY"],
                    "sell_count": counts["SELL"],
                    "hold_count": counts["HOLD"],
                    "not_run_count": counts["NOT_RUN"],
                    "na_count": counts["N/A"],
                    "no_data_count": counts["NO_DATA"],
                    "missing_count": counts["MISSING"],
                    "applicable_rows": int(applicable - counts["NO_DATA"]),
                    "active_signal_count": int(counts["BUY"] + counts["SELL"]),
                }
            )

    return pd.DataFrame(rows)


def _active_signal_text(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "symbol" not in frame.columns:
        return {}
    strategy_columns = [name for name in list_strategy_names() if name in frame.columns]
    mapping: dict[str, str] = {}
    for _, row in frame.iterrows():
        active_items = [f"{strategy}={row[strategy]}" for strategy in strategy_columns if str(row.get(strategy, "")) in {"BUY", "SELL"}]
        mapping[str(row.get("symbol", ""))] = " | ".join(active_items) if active_items else "NONE"
    return mapping


def build_action_focus_frame(summary: pd.DataFrame, matrix_frames: dict[str, pd.DataFrame], preclose: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=ACTION_FOCUS_COLUMNS)

    focus = summary.copy()
    for column in ["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket", "dashboard_action"]:
        if column not in focus.columns:
            focus[column] = pd.Series(dtype="string")

    focus_columns = ["conviction_rank", "symbol", "display_symbol", "name", "asset_type", "bucket", "dashboard_action"]
    focus = focus[focus_columns]
    focus["eod_d_active"] = focus["symbol"].map(_active_signal_text(matrix_frames.get("EOD_D_Matrix", pd.DataFrame()))).fillna("NONE")
    focus["eod_w_active"] = focus["symbol"].map(_active_signal_text(matrix_frames.get("EOD_W_Matrix", pd.DataFrame()))).fillna("NONE")
    focus["eod_m_active"] = focus["symbol"].map(_active_signal_text(matrix_frames.get("EOD_M_Matrix", pd.DataFrame()))).fillna("NONE")
    focus["intraday_active"] = focus["symbol"].map(_active_signal_text(matrix_frames.get("INTRADAY_Matrix", pd.DataFrame()))).fillna("NONE")

    preclose_copy = preclose.copy()
    if preclose_copy.empty:
        focus["preclose_signal"] = pd.Series(dtype="string")
        focus["preclose_score"] = pd.Series(dtype="float64")
    else:
        preclose_subset = preclose_copy[[column for column in ["symbol", "decision_signal", "decision_score"] if column in preclose_copy.columns]].rename(
            columns={"decision_signal": "preclose_signal", "decision_score": "preclose_score"}
        )
        focus = focus.merge(preclose_subset, on="symbol", how="left")

    if "preclose_signal" not in focus.columns:
        focus["preclose_signal"] = pd.Series(dtype="string")
    if "preclose_score" not in focus.columns:
        focus["preclose_score"] = pd.Series(dtype="float64")

    active_columns = ["eod_d_active", "eod_w_active", "eod_m_active", "intraday_active"]
    focus["active_mode_count"] = sum((focus[column] != "NONE").astype(int) for column in active_columns) + focus["preclose_signal"].isin(["BUY", "SELL"]).astype(int)
    focus = focus[focus["active_mode_count"] > 0].reset_index(drop=True)
    focus = _sort_report_rows(focus)
    for column in ACTION_FOCUS_COLUMNS:
        if column not in focus.columns:
            focus[column] = pd.Series(dtype="string")
    return focus[ACTION_FOCUS_COLUMNS]


def build_strategy_report_frames(
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
) -> dict[str, pd.DataFrame]:
    no_data_symbols = {symbol for symbol, frame in (market_data_by_symbol or {}).items() if frame.empty}
    summary_full = _complete_summary_frame(summary, fallback_symbols=fallback_symbols, no_data_symbols=no_data_symbols, has_intraday=intraday_ts is not None)
    eod_d_matrix = build_strategy_signal_matrix(summary_full, eod_d, supported_mode="eod", no_data_symbols=no_data_symbols, fallback_symbols=fallback_symbols)
    eod_w_matrix = build_strategy_signal_matrix(summary_full, eod_w, supported_mode="eod", no_data_symbols=no_data_symbols, fallback_symbols=fallback_symbols)
    eod_m_matrix = build_strategy_signal_matrix(summary_full, eod_m, supported_mode="eod", no_data_symbols=no_data_symbols, fallback_symbols=fallback_symbols)
    intraday_matrix = build_strategy_signal_matrix(summary_full, intraday, supported_mode="intraday", no_data_symbols=no_data_symbols, fallback_symbols=fallback_symbols) if intraday_ts is not None else pd.DataFrame(columns=MATRIX_META_COLUMNS + list_strategy_names())
    matrix_frames = {
        "EOD_D_Matrix": eod_d_matrix,
        "EOD_W_Matrix": eod_w_matrix,
        "EOD_M_Matrix": eod_m_matrix,
        "INTRADAY_Matrix": intraday_matrix,
    }

    symbol_summary = summary_full.copy()
    if not preclose.empty:
        preclose_subset = preclose[[column for column in ["symbol", "decision_signal", "decision_score", "decision_reason", "trend_state"] if column in preclose.columns]].rename(
            columns={
                "decision_signal": "preclose_signal",
                "decision_score": "preclose_score",
                "decision_reason": "preclose_reason",
                "trend_state": "preclose_trend_state",
            }
        )
        symbol_summary = symbol_summary.merge(preclose_subset, on="symbol", how="left")
    symbol_summary = _sort_report_rows(symbol_summary)
    for column in SUMMARY_SHEET_COLUMNS:
        if column not in symbol_summary.columns:
            symbol_summary[column] = pd.Series(dtype="string")

    preclose_sheet = preclose.copy()
    preclose_sheet = _sort_report_rows(preclose_sheet)
    for column in PRE_CLOSE_SHEET_COLUMNS:
        if column not in preclose_sheet.columns:
            preclose_sheet[column] = pd.Series(dtype="string")

    action_focus = build_action_focus_frame(summary=summary_full, matrix_frames=matrix_frames, preclose=preclose)

    overview_rows = [
        {"section": "report", "item": "generated_at", "value": now_shanghai().isoformat()},
        {"section": "report", "item": "signal_date", "value": signal_date.isoformat()},
        {"section": "report", "item": "eod_d_date", "value": _sheet_signal_date_value(eod_d)},
        {"section": "report", "item": "eod_w_date", "value": _sheet_signal_date_value(eod_w)},
        {"section": "report", "item": "eod_m_date", "value": _sheet_signal_date_value(eod_m)},
        {"section": "report", "item": "intraday_ts", "value": intraday_ts.isoformat() if intraday_ts is not None else "NONE"},
        {"section": "report", "item": "symbol_count", "value": str(len(summary_full.index))},
        {"section": "report", "item": "strategy_count", "value": str(len(list_strategy_names()))},
        {"section": "report", "item": "no_data_symbol_count", "value": str(len(no_data_symbols))},
        {"section": "legend", "item": "BUY", "value": "策略给出买入结论"},
        {"section": "legend", "item": "SELL", "value": "策略给出卖出结论"},
        {"section": "legend", "item": "HOLD", "value": "策略已运行但结论为观望"},
        {"section": "legend", "item": "NOT_RUN", "value": "该模式下该策略没有运行"},
        {"section": "legend", "item": "N/A", "value": "该策略不适用于该标的类型"},
        {"section": "legend", "item": "NO_DATA", "value": "该标的缺少历史行情，策略无法生成信号"},
        {"section": "legend", "item": "MISSING", "value": "理论应有结果但当前缺失，提示上游检查"},
        {"section": "sheet", "item": "EOD_D_Matrix", "value": "日频策略矩阵"},
        {"section": "sheet", "item": "EOD_W_Matrix", "value": "周频策略矩阵"},
        {"section": "sheet", "item": "EOD_M_Matrix", "value": "月频策略矩阵"},
        {"section": "sheet", "item": "INTRADAY_Matrix", "value": "同交易日盘中策略矩阵；若无则为空"},
        {"section": "sheet", "item": "PRE_CLOSE_View", "value": "收盘前决策视图"},
        {"section": "sheet", "item": "Action_Focus", "value": "仅保留非 HOLD 的重点动作视图"},
        {"section": "sheet", "item": "Symbol_Summary", "value": "标的级综合摘要"},
        {"section": "sheet", "item": "Strategy_Stats", "value": "策略在各矩阵中的统计"},
        {"section": "sheet", "item": "Hypothesis_Stats", "value": "按策略哲学分组后的矩阵统计"},
    ]

    frames: dict[str, pd.DataFrame] = {
        "Overview": pd.DataFrame(overview_rows),
        "Action_Focus": action_focus,
        "Symbol_Summary": symbol_summary[[column for column in SUMMARY_SHEET_COLUMNS + ["preclose_signal", "preclose_score", "preclose_reason", "preclose_trend_state"] if column in symbol_summary.columns]],
        "Strategy_Stats": build_strategy_statistics(matrix_frames),
        "Hypothesis_Stats": build_hypothesis_statistics(matrix_frames),
        "EOD_D_Matrix": eod_d_matrix,
        "EOD_W_Matrix": eod_w_matrix,
        "EOD_M_Matrix": eod_m_matrix,
        "INTRADAY_Matrix": intraday_matrix,
        "PRE_CLOSE_View": preclose_sheet[PRE_CLOSE_SHEET_COLUMNS],
    }
    return frames


def _apply_text_signal_format(workbook, worksheet, first_row: int, last_row: int, first_col: int, last_col: int) -> None:
    if last_row < first_row or last_col < first_col:
        return
    formats = {
        "BUY": workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"}),
        "SELL": workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"}),
        "HOLD": workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"}),
        "NOT_RUN": workbook.add_format({"bg_color": "#D9D9D9", "font_color": "#444444"}),
        "N/A": workbook.add_format({"bg_color": "#EFEFEF", "font_color": "#666666"}),
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


def _set_column_widths(worksheet, frame: pd.DataFrame, max_width: int = 28) -> None:
    for index, column in enumerate(frame.columns):
        series = frame[column].astype(str) if column in frame.columns else pd.Series(dtype="string")
        content_width = int(series.map(len).max()) if not frame.empty else 0
        width = min(max(len(str(column)) + 2, content_width + 2, 12), max_width)
        worksheet.set_column(index, index, width)


def _sheet_signal_date_value(frame: pd.DataFrame) -> str:
    if frame.empty or "date" not in frame.columns or frame["date"].empty:
        return "NONE"
    return str(frame["date"].astype(str).iloc[0])


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


def _write_strategy_matrix_workbook(output_path: Path, frames: dict[str, pd.DataFrame], engine: Literal["xlsxwriter"]) -> None:
    with pd.ExcelWriter(output_path, engine=engine) as writer:
        workbook = cast(Any, writer.book)
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = cast(Any, writer.sheets[sheet_name])
            _set_column_widths(worksheet, frame, max_width=48 if sheet_name == "Action_Focus" else 28)
            worksheet.set_row(0, 22, header_format)
            if not frame.empty:
                worksheet.autofilter(0, 0, len(frame.index), len(frame.columns) - 1)
            if sheet_name.endswith("_Matrix"):
                meta_col_count = len(MATRIX_META_COLUMNS)
                worksheet.freeze_panes(1, meta_col_count)
                _apply_text_signal_format(workbook, worksheet, 1, len(frame.index), meta_col_count, len(frame.columns) - 1)
            elif sheet_name == "Action_Focus":
                worksheet.freeze_panes(1, 4)
                signal_columns = [index for index, column in enumerate(frame.columns) if column in {"eod_d_active", "eod_w_active", "eod_m_active", "intraday_active", "preclose_signal"}]
                for column_index in signal_columns:
                    _apply_text_signal_format(workbook, worksheet, 1, len(frame.index), column_index, column_index)
            elif sheet_name == "Symbol_Summary":
                worksheet.freeze_panes(1, 4)
                signal_columns = [index for index, column in enumerate(frame.columns) if column in {"eod_d", "eod_w", "eod_m", "intraday", "preclose_signal"}]
                for column_index in signal_columns:
                    _apply_text_signal_format(workbook, worksheet, 1, len(frame.index), column_index, column_index)
            elif sheet_name == "PRE_CLOSE_View":
                worksheet.freeze_panes(1, 4)
                if "decision_signal" in frame.columns:
                    column_index = frame.columns.get_loc("decision_signal")
                    if isinstance(column_index, int):
                        _apply_text_signal_format(workbook, worksheet, 1, len(frame.index), column_index, column_index)
            else:
                worksheet.freeze_panes(1, 1)


def export_strategy_matrix_workbook(
    frames: dict[str, pd.DataFrame],
    signal_date: date,
    intraday_ts: datetime | None,
    output_dir: str | Path = "reports/strategy_matrix",
) -> Path:
    engine = _resolve_excel_engine()
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = intraday_ts.strftime("%Y%m%d_%H%M") if intraday_ts is not None else signal_date.strftime("%Y%m%d")
    output_path = folder / f"strategy_matrix_{suffix}.xlsx"
    try:
        _write_strategy_matrix_workbook(output_path=output_path, frames=frames, engine=engine)
        return output_path
    except PermissionError:
        fallback_suffix = now_shanghai().strftime("%Y%m%d_%H%M%S")
        fallback_path = folder / f"strategy_matrix_{suffix}_{fallback_suffix}.xlsx"
        _write_strategy_matrix_workbook(output_path=fallback_path, frames=frames, engine=engine)
        return fallback_path
    return output_path


def export_strategy_matrix_report(
    signal_date: date | None = None,
    intraday_ts: datetime | None = None,
    intraday_bar_frequency: str = "5",
    output_dir: str | Path = "reports/strategy_matrix",
    config: PostgresConfig | None = None,
) -> dict[str, object]:
    universe = load_universe_config()
    universe_symbols = sorted(set(universe.index_symbols + universe.etf_symbols))
    with session_scope(config) as session:
        reference_date = signal_date or latest_closed_trading_date()
        signal_dates = _resolve_eod_signal_dates(session, requested_date=reference_date)
        target_date = signal_dates["D"] or reference_date
        latest_intraday_ts = intraday_ts or load_latest_intraday_signal_ts(session, bar_frequency=intraday_bar_frequency)
        target_ts = latest_intraday_ts if latest_intraday_ts is not None and latest_intraday_ts.date() == target_date else None
        eod_d = load_signals_by_date(session, signal_dates["D"], mode="eod", bar_frequency="D") if signal_dates["D"] is not None else pd.DataFrame()
        eod_w = load_signals_by_date(session, signal_dates["W"], mode="eod", bar_frequency="W") if signal_dates["W"] is not None else pd.DataFrame()
        eod_m = load_signals_by_date(session, signal_dates["M"], mode="eod", bar_frequency="M") if signal_dates["M"] is not None else pd.DataFrame()
        intraday = load_intraday_signals(session, target_ts, bar_frequency=intraday_bar_frequency) if target_ts is not None else pd.DataFrame()
        market_data_by_symbol = load_market_prices_map(session, universe_symbols, limit=240, as_of_date=target_date) if universe_symbols else {}

    secondary_validation = build_secondary_validation(eod_d, market_data_by_symbol=market_data_by_symbol, signal_date=target_date)
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
        intraday_bars_by_symbol=None,
        analysis_mode="POST_CLOSE",
        signal_date=target_date,
        analysis_ts=None,
        fallback_symbols=universe_symbols,
    )
    frames = build_strategy_report_frames(
        summary=summary,
        eod_d=eod_d,
        eod_w=eod_w,
        eod_m=eod_m,
        intraday=intraday,
        preclose=preclose,
        signal_date=target_date,
        intraday_ts=target_ts,
        market_data_by_symbol=market_data_by_symbol,
        fallback_symbols=universe_symbols,
    )
    workbook_path = export_strategy_matrix_workbook(frames=frames, signal_date=target_date, intraday_ts=target_ts, output_dir=output_dir)
    return {
        "signal_date": target_date.isoformat(),
        "signal_date_d": signal_dates["D"].isoformat() if signal_dates["D"] is not None else None,
        "signal_date_w": signal_dates["W"].isoformat() if signal_dates["W"] is not None else None,
        "signal_date_m": signal_dates["M"].isoformat() if signal_dates["M"] is not None else None,
        "intraday_ts": target_ts.isoformat() if target_ts is not None else None,
        "sheet_names": list(frames.keys()),
        "symbol_rows": int(len(frames["Symbol_Summary"].index)),
        "strategy_count": int(len(list_strategy_names())),
        "includes_intraday": bool(target_ts is not None),
        "xlsx_path": str(workbook_path),
    }
