from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import PROJECT_ROOT, SymbolMeta, load_runtime_config, load_symbol_meta_map, load_universe_config
from core.clock import now_shanghai
from core.trading_calendar import latest_closed_trading_date
from data_storage.database import session_scope
from data_storage.realtime_repository import load_realtime_bars_map
from data_storage.repository import load_market_prices_map


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _latest_matching_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    matches = [path for path in directory.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: (path.name, path.stat().st_mtime_ns))


def _latest_matching_file_filtered(directory: Path, pattern: str, exclude_substring: str) -> Path | None:
    if not directory.exists():
        return None
    matches = [path for path in directory.glob(pattern) if path.is_file() and exclude_substring not in path.name]
    if not matches:
        return None
    return max(matches, key=lambda path: (path.name, path.stat().st_mtime_ns))


def _safe_read_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(
        path,
        dtype={
            "symbol": "string",
            "display_symbol": "string",
            "previous_dashboard_action": "string",
            "dashboard_action": "string",
            "intraday": "string",
            "signal": "string",
        },
    )


def _normalize_json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _frame_to_records(frame: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clipped = frame.head(max(0, limit)).copy()
    records: list[dict[str, Any]] = []
    for row in clipped.to_dict("records"):
        records.append({str(key): _normalize_json_value(value) for key, value in row.items()})
    return records


def _resolve_report_root(report_root: Path | str | None) -> Path:
    if report_root is None:
        return PROJECT_ROOT / "reports"
    return Path(report_root)


def _serialize_path(path: Path | None) -> str | None:
    return None if path is None else str(path)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "nat", "none", "<na>"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _pct_delta(current: float | None, reference: float | None) -> float | None:
    if current is None or reference is None or reference == 0:
        return None
    return float((current / reference) - 1.0)


def _quote_key(asset_type: str) -> str:
    return "current_level" if asset_type == "INDEX" else "current_price"


def _safe_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "nat", "none", "<na>"}:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{text}T00:00:00")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
    return parsed


def _quote_reference_date() -> date:
    current = now_shanghai()
    if current.weekday() >= 5:
        return latest_closed_trading_date(current)
    return current.date()


def _base_quote_row(symbol: str, asset_type: str, meta: SymbolMeta | None) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "display_symbol": meta.display_symbol if meta is not None else symbol,
        "name": meta.name if meta is not None else symbol,
        _quote_key(asset_type): None,
        "prev_close": None,
        "change_value": None,
        "change_pct": None,
        "quote_source": "无数据 / No Data",
        "updated_at": None,
    }


def _latest_previous_close(daily_frame: pd.DataFrame, current_date: date | None = None) -> float | None:
    if daily_frame.empty or "close" not in daily_frame.columns:
        return None

    ordered_daily = daily_frame.sort_values("date").copy()
    ordered_daily["date"] = pd.to_datetime(ordered_daily["date"], errors="coerce")
    ordered_daily["close"] = pd.to_numeric(ordered_daily["close"], errors="coerce")
    ordered_daily = ordered_daily.dropna(subset=["date", "close"])
    if ordered_daily.empty:
        return None

    if current_date is not None:
        eligible = ordered_daily[ordered_daily["date"].dt.date < current_date]
        if not eligible.empty:
            return _safe_float(eligible.iloc[-1].get("close"))

    if len(ordered_daily.index) >= 2:
        return _safe_float(ordered_daily.iloc[-2].get("close"))
    return None


def _build_live_quote_row(
    symbol: str,
    asset_type: str,
    meta: SymbolMeta | None,
    daily_frame: pd.DataFrame,
    intraday_frame: pd.DataFrame,
) -> dict[str, Any]:
    row = _base_quote_row(symbol=symbol, asset_type=asset_type, meta=meta)
    key = _quote_key(asset_type)

    ordered_intraday = intraday_frame.sort_values("date").copy() if not intraday_frame.empty else pd.DataFrame()
    if not ordered_intraday.empty:
        ordered_intraday["date"] = pd.to_datetime(ordered_intraday["date"], errors="coerce")
        ordered_intraday["close"] = pd.to_numeric(ordered_intraday["close"], errors="coerce")
        ordered_intraday = ordered_intraday.dropna(subset=["date", "close"])
        if not ordered_intraday.empty:
            latest_intraday = ordered_intraday.iloc[-1]
            current_value = _safe_float(latest_intraday.get("close"))
            current_date = latest_intraday["date"].date()
            prev_close = _latest_previous_close(daily_frame, current_date=current_date)
            row[key] = current_value
            row["prev_close"] = prev_close
            row["change_value"] = None if current_value is None or prev_close is None else float(current_value - prev_close)
            row["change_pct"] = _pct_delta(current_value, prev_close)
            row["quote_source"] = "实时快照 / Intraday"
            row["updated_at"] = latest_intraday["date"].isoformat()
            return row

    if daily_frame.empty:
        return row

    ordered_daily = daily_frame.sort_values("date").copy()
    ordered_daily["date"] = pd.to_datetime(ordered_daily["date"], errors="coerce")
    ordered_daily["close"] = pd.to_numeric(ordered_daily["close"], errors="coerce")
    ordered_daily = ordered_daily.dropna(subset=["date", "close"])
    if ordered_daily.empty:
        return row

    latest_daily = ordered_daily.iloc[-1]
    current_value = _safe_float(latest_daily.get("close"))
    prev_close = _latest_previous_close(ordered_daily)
    row[key] = current_value
    row["prev_close"] = prev_close
    row["change_value"] = None if current_value is None or prev_close is None else float(current_value - prev_close)
    row["change_pct"] = _pct_delta(current_value, prev_close)
    row["quote_source"] = "收盘价格 / Daily Close"
    row["updated_at"] = latest_daily["date"].date().isoformat()
    return row


def _merge_preclose_fallback(
    row: dict[str, Any],
    asset_type: str,
    preclose_by_symbol: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(row.get("symbol", ""))
    preclose_row = preclose_by_symbol.get(symbol)
    if preclose_row is None:
        return row

    key = _quote_key(asset_type)
    latest_price = _safe_float(preclose_row.get("latest_price"))
    prev_close = _safe_float(preclose_row.get("prev_close"))
    change_pct = _safe_float(preclose_row.get("day_change_pct"))
    row_updated_at = _safe_timestamp(row.get("updated_at"))
    preclose_updated_at = _safe_timestamp(preclose_row.get("analysis_ts")) or _safe_timestamp(preclose_row.get("signal_date"))
    should_override_with_preclose = (
        latest_price is not None
        and (
            row.get(key) is None
            or row_updated_at is None
            or (preclose_updated_at is not None and row_updated_at < preclose_updated_at)
        )
    )

    if should_override_with_preclose:
        row[key] = latest_price
    if (row.get("prev_close") is None or should_override_with_preclose) and prev_close is not None:
        row["prev_close"] = prev_close
    if (row.get("change_value") is None or should_override_with_preclose) and latest_price is not None and prev_close is not None:
        row["change_value"] = float(latest_price - prev_close)
    if (row.get("change_pct") is None or should_override_with_preclose) and change_pct is not None:
        row["change_pct"] = change_pct
    if should_override_with_preclose:
        row["quote_source"] = "预收盘快照 / Preclose Snapshot"
    elif row.get("quote_source") == "无数据 / No Data" and latest_price is not None:
        row["quote_source"] = "预收盘缓存 / Preclose Cache"
    if row.get("updated_at") is None or should_override_with_preclose:
        row["updated_at"] = preclose_row.get("analysis_ts") or preclose_row.get("signal_date")
    return row


def _sort_quote_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(row: dict[str, Any]) -> tuple[bool, float, str]:
        change_pct = _safe_float(row.get("change_pct"))
        symbol = str(row.get("symbol", ""))
        if change_pct is None:
            return (True, 0.0, symbol)
        return (False, -change_pct, symbol)

    return sorted(rows, key=_sort_key)


def _mark_stale_quote(row: dict[str, Any], reference_date: date) -> dict[str, Any]:
    updated_at = _safe_timestamp(row.get("updated_at"))
    if updated_at is None or updated_at.date() >= reference_date:
        return row

    source = str(row.get("quote_source", ""))
    if source == "实时快照 / Intraday":
        row["quote_source"] = "旧盘中快照 / Stale Intraday"
    elif source == "收盘价格 / Daily Close":
        row["quote_source"] = "旧收盘价格 / Stale Daily Close"
    return row


def _split_quote_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    gainers: list[dict[str, Any]] = []
    losers: list[dict[str, Any]] = []
    flat: list[dict[str, Any]] = []

    for row in rows:
        change_pct = _safe_float(row.get("change_pct"))
        if change_pct is None or change_pct == 0:
            flat.append(row)
        elif change_pct > 0:
            gainers.append(row)
        else:
            losers.append(row)

    gainers = _sort_quote_rows(gainers)
    losers = sorted(losers, key=lambda row: (_safe_float(row.get("change_pct")) or 0.0, str(row.get("symbol", ""))))
    flat = sorted(flat, key=lambda row: str(row.get("symbol", "")))
    return {
        "gainers": gainers,
        "losers": losers,
        "flat": flat,
    }


def _build_market_overview_tables(preclose: pd.DataFrame) -> dict[str, Any]:
    universe = load_universe_config()
    symbol_meta_map = load_symbol_meta_map()
    runtime = load_runtime_config()
    snapshot_today = _quote_reference_date()
    all_symbols = list(universe.index_symbols) + list(universe.etf_symbols)
    preclose_rows = _frame_to_records(preclose, limit=max(len(preclose.index), 1_000))
    preclose_by_symbol = {
        str(record.get("symbol", "")): record for record in preclose_rows if str(record.get("symbol", "")).strip()
    }

    market_data_by_symbol: dict[str, pd.DataFrame] = {}
    intraday_bars_by_symbol: dict[str, pd.DataFrame] = {}
    quote_error: str | None = None
    quote_status = "实时数据库 / Live DB"

    try:
        with session_scope() as session:
            if all_symbols:
                market_data_by_symbol = load_market_prices_map(session, all_symbols, limit=240)
                intraday_bars_by_symbol = load_realtime_bars_map(
                    session,
                    symbols=all_symbols,
                    bar_frequency=runtime.intraday_bar_frequency,
                    limit=64,
                )
    except Exception as exc:
        quote_status = "预收盘回退 / Preclose Fallback"
        quote_error = f"{exc.__class__.__name__}: {exc}"

    def _rows_for_symbols(symbols: list[str], asset_type: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            meta = symbol_meta_map.get(symbol)
            row = _build_live_quote_row(
                symbol=symbol,
                asset_type=asset_type,
                meta=meta,
                daily_frame=market_data_by_symbol.get(symbol, pd.DataFrame()),
                intraday_frame=intraday_bars_by_symbol.get(symbol, pd.DataFrame()),
            )
            row = _merge_preclose_fallback(row, asset_type=asset_type, preclose_by_symbol=preclose_by_symbol)
            rows.append(_mark_stale_quote(row, reference_date=snapshot_today))
        return _sort_quote_rows(rows)

    index_quotes = _rows_for_symbols(list(universe.index_symbols), asset_type="INDEX")
    etf_quotes = _rows_for_symbols(list(universe.etf_symbols), asset_type="ETF")
    index_split = _split_quote_rows(index_quotes)
    etf_split = _split_quote_rows(etf_quotes)

    return {
        "quote_status": quote_status,
        "quote_error": quote_error,
        "quote_bar_frequency": runtime.intraday_bar_frequency,
        "index_quotes": index_quotes,
        "etf_quotes": etf_quotes,
        "index_quote_gainers": index_split["gainers"],
        "index_quote_losers": index_split["losers"],
        "index_quote_flat": index_split["flat"],
        "etf_quote_gainers": etf_split["gainers"],
        "etf_quote_losers": etf_split["losers"],
        "etf_quote_flat": etf_split["flat"],
    }


def _build_provider_status() -> dict[str, Any]:
    runtime = load_runtime_config()
    hk_provider = runtime.hk_realtime_provider
    hk_symbol_map = runtime.hk_realtime_futu_symbol_map or {}
    return {
        "mainland_provider": "pytdx",
        "fallback_provider": "akshare",
        "hk_provider": hk_provider,
        "hk_futu_host": runtime.hk_realtime_futu_host,
        "hk_futu_port": runtime.hk_realtime_futu_port,
        "hk_futu_is_encrypt": runtime.hk_realtime_futu_is_encrypt,
        "hk_symbol_map_size": len(hk_symbol_map),
        "hk_status": "configured" if hk_provider != "none" else "disabled",
    }


def _column_as_string_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype="string")
    data = frame.loc[:, column]
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return pd.Series(dtype="string")
        data = cast(pd.DataFrame, data).iloc[:, 0]
    return cast(pd.Series, data).astype(str)


def _ensure_frame(table: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if isinstance(table, pd.Series):
        return table.to_frame()
    return table


def _build_hypothesis_focus(conclusion: pd.DataFrame) -> pd.DataFrame:
    if conclusion.empty or "symbol" not in conclusion.columns:
        return pd.DataFrame()

    table = conclusion.copy()
    if "hypothesis_consensus_action" not in table.columns:
        return pd.DataFrame()

    focus_mask = table["hypothesis_tiebreak_applied"].fillna(False).astype(bool) if "hypothesis_tiebreak_applied" in table.columns else pd.Series(False, index=table.index)
    consensus_mask = table["hypothesis_consensus_action"].astype(str).isin(["BUY", "SELL"])
    table = _ensure_frame(table[focus_mask | consensus_mask].copy())
    if table.empty:
        return pd.DataFrame()

    if "hypothesis_summary_text" not in table.columns:
        table["hypothesis_summary_text"] = pd.Series(dtype="string")
    if "conviction_rank" in table.columns:
        table["conviction_rank"] = pd.to_numeric(table["conviction_rank"], errors="coerce")
        if "symbol" in table.columns:
            table = table.sort_values(by=["symbol"], ascending=[True])
        table = table.sort_values(by=["conviction_rank"], ascending=[True], kind="stable")
    return table


def build_dashboard_snapshot(report_root: Path | str | None = None) -> dict[str, Any]:
    root = _resolve_report_root(report_root)
    summary_dir = root / "summary"
    intraday_dir = root / "intraday"
    preclose_dir = root / "preclose"
    daily_conclusion_dir = root / "daily_conclusion"

    summary_path = _latest_matching_file(summary_dir, "signal_summary_*.csv")
    push_path = _latest_matching_file(summary_dir, "signal_push_candidates_*.csv")
    top_path = _latest_matching_file(summary_dir, "signal_top_candidates_*.csv")
    group_path = _latest_matching_file(summary_dir, "signal_group_summary_*.csv")
    intraday_path = _latest_matching_file(intraday_dir, "signals_*.csv")
    preclose_path = _latest_matching_file(preclose_dir, "preclose_decision_*.csv")
    daily_conclusion_path = _latest_matching_file_filtered(daily_conclusion_dir, "daily_conclusion_*.csv", "operation")

    summary = _safe_read_csv(summary_path)
    push_candidates = _safe_read_csv(push_path)
    top_candidates = _safe_read_csv(top_path)
    group_summary = _safe_read_csv(group_path)
    intraday_signals = _safe_read_csv(intraday_path)
    preclose = _safe_read_csv(preclose_path)
    daily_conclusion = _safe_read_csv(daily_conclusion_path)
    market_overview = _build_market_overview_tables(preclose=preclose)
    hypothesis_focus = _build_hypothesis_focus(daily_conclusion)

    action_focus = summary.copy()
    if not action_focus.empty:
        if "dashboard_action" in action_focus.columns:
            action_focus = _ensure_frame(action_focus[action_focus["dashboard_action"].astype(str) != "NEUTRAL"])
        if "conviction_rank" in action_focus.columns:
            if "symbol" in action_focus.columns:
                action_focus = action_focus.sort_values(by=["symbol"], ascending=[True])
            action_focus = action_focus.sort_values(by=["conviction_rank"], ascending=[True], kind="stable")

    latest_intraday = intraday_signals.copy()
    if not latest_intraday.empty:
        sort_columns = [column for column in ["ts", "symbol", "strategy"] if column in latest_intraday.columns]
        if sort_columns:
            for column in reversed(sort_columns[1:]):
                latest_intraday = latest_intraday.sort_values(by=column, ascending=True, kind="stable")
            latest_intraday = latest_intraday.sort_values(by=sort_columns[0], ascending=False, kind="stable")

    intraday_series = _column_as_string_series(summary, "intraday")
    dashboard_action_series = _column_as_string_series(summary, "dashboard_action")

    metrics = {
        "summary_rows": int(len(summary.index)),
        "intraday_signal_rows": int(len(intraday_signals.index)),
        "push_rows": int(len(push_candidates.index)),
        "top_rows": int(len(top_candidates.index)),
        "preclose_rows": int(len(preclose.index)),
        "hypothesis_focus_rows": int(len(hypothesis_focus.index)),
        "index_quote_rows": int(len(market_overview["index_quotes"])),
        "etf_quote_rows": int(len(market_overview["etf_quotes"])),
        "active_intraday_count": int(intraday_series.isin(["BUY", "SELL"]).sum()) if not summary.empty else 0,
        "priority_action_count": int(dashboard_action_series.isin(["PRIORITY_BUY", "PRIORITY_SELL"]).sum()) if not summary.empty else 0,
    }

    provider_status = _build_provider_status()
    provider_status["quote_status"] = market_overview["quote_status"]
    provider_status["quote_error"] = market_overview["quote_error"]
    provider_status["quote_bar_frequency"] = market_overview["quote_bar_frequency"]

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "report_root": str(root),
        "provider_status": provider_status,
        "latest_files": {
            "summary_path": _serialize_path(summary_path),
            "push_path": _serialize_path(push_path),
            "top_path": _serialize_path(top_path),
            "group_path": _serialize_path(group_path),
            "intraday_path": _serialize_path(intraday_path),
            "preclose_path": _serialize_path(preclose_path),
            "daily_conclusion_path": _serialize_path(daily_conclusion_path),
        },
        "metrics": metrics,
        "tables": {
            "index_quotes": market_overview["index_quotes"],
            "etf_quotes": market_overview["etf_quotes"],
            "index_quote_gainers": market_overview["index_quote_gainers"],
            "index_quote_losers": market_overview["index_quote_losers"],
            "index_quote_flat": market_overview["index_quote_flat"],
            "etf_quote_gainers": market_overview["etf_quote_gainers"],
            "etf_quote_losers": market_overview["etf_quote_losers"],
            "etf_quote_flat": market_overview["etf_quote_flat"],
            "action_focus": _frame_to_records(_ensure_frame(action_focus), limit=12),
            "hypothesis_focus": _frame_to_records(_ensure_frame(hypothesis_focus), limit=12),
            "summary": _frame_to_records(_ensure_frame(summary), limit=20),
            "latest_intraday": _frame_to_records(_ensure_frame(latest_intraday), limit=20),
            "push_candidates": _frame_to_records(_ensure_frame(push_candidates), limit=10),
            "top_candidates": _frame_to_records(_ensure_frame(top_candidates), limit=10),
            "group_summary": _frame_to_records(_ensure_frame(group_summary), limit=10),
            "preclose": _frame_to_records(_ensure_frame(preclose), limit=10),
        },
    }


def refresh_dashboard_snapshot(report_root: Path | str | None = None) -> dict[str, Any]:
    from core.clock import now_shanghai
    from scheduler.intraday_runner import run_intraday_iteration
    from signal_service.daily_conclusion_report import export_daily_conclusion_report

    refresh_ts = now_shanghai()
    refresh_result = run_intraday_iteration()
    refresh_result["daily_conclusion_result"] = export_daily_conclusion_report(signal_date=refresh_ts.date(), intraday_ts=refresh_ts)
    snapshot = build_dashboard_snapshot(report_root=report_root)
    snapshot["refresh_result"] = refresh_result
    return snapshot
