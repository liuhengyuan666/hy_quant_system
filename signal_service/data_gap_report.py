from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from config.settings import PostgresConfig, load_universe_config
from core.clock import now_shanghai
from signal_service.daily_conclusion_report import (
    ACTION_COLUMNS,
    _apply_action_format,
    _resolve_excel_engine,
    _set_column_widths,
    build_daily_conclusion_frames,
    load_daily_conclusion_context,
)

DATA_GAP_STATUS_ORDER = ["NO_DATA", "PARTIAL", "OK"]
DATA_GAP_DETAIL_COLUMNS = [
    "conviction_rank",
    "symbol",
    "display_symbol",
    "name",
    "asset_type",
    "bucket",
    "market_data_rows",
    "data_status",
    "missing_horizons",
    "reason",
    "long_term_action",
    "short_term_action",
    "preclose_signal",
    "overall_action",
]


def _missing_horizons(row: pd.Series) -> str:
    if str(row.get("data_status", "OK")) == "NO_DATA":
        return "long_term,short_term"
    missing: list[str] = []
    if str(row.get("long_term_action", "HOLD")) == "MISSING":
        missing.append("long_term")
    if str(row.get("short_term_action", "HOLD")) == "MISSING":
        missing.append("short_term")
    return ",".join(missing) if missing else "NONE"


def _gap_reason(row: pd.Series) -> str:
    data_status = str(row.get("data_status", "OK"))
    missing_horizons = str(row.get("missing_horizons", "NONE"))
    if data_status == "NO_DATA":
        return "缺少历史行情"
    if data_status != "PARTIAL":
        return "状态正常"
    if missing_horizons == "long_term":
        return "缺少长线策略信号"
    if missing_horizons == "short_term":
        return "缺少短线策略信号"
    if missing_horizons == "long_term,short_term":
        return "长线和短线策略信号均缺失"
    return "部分策略信号缺失"


def _overview_count_rows(frame: pd.DataFrame, column: str, section: str, value_order: list[str]) -> list[dict[str, str]]:
    if frame.empty or column not in frame.columns:
        return [{"section": section, "item": value, "value": "0"} for value in value_order]
    counts = frame[column].astype(str).value_counts(dropna=False)
    return [{"section": section, "item": value, "value": str(int(counts.get(value, 0)))} for value in value_order]


def build_universe_status_frame(
    conclusion: pd.DataFrame,
    market_data_by_symbol: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if conclusion.empty:
        return pd.DataFrame(columns=DATA_GAP_DETAIL_COLUMNS)
    table = conclusion.copy()
    table["market_data_rows"] = table["symbol"].astype(str).map(
        lambda symbol: int(len((market_data_by_symbol or {}).get(symbol, pd.DataFrame()).index))
    )
    table["missing_horizons"] = table.apply(_missing_horizons, axis=1)
    table["reason"] = table.apply(_gap_reason, axis=1)
    for column in DATA_GAP_DETAIL_COLUMNS:
        if column not in table.columns:
            table[column] = pd.Series(dtype="string")
    return table[DATA_GAP_DETAIL_COLUMNS].reset_index(drop=True)


def build_data_gap_report_frames(
    conclusion: pd.DataFrame,
    signal_date: date,
    signal_dates: dict[str, date | None] | None = None,
    intraday_ts: datetime | None = None,
    market_data_by_symbol: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.DataFrame]:
    universe_status = build_universe_status_frame(conclusion, market_data_by_symbol=market_data_by_symbol)
    data_gaps = universe_status[universe_status["data_status"].isin(["NO_DATA", "PARTIAL"])].reset_index(drop=True)
    no_data_count = int((universe_status.get("data_status") == "NO_DATA").sum()) if not universe_status.empty else 0
    partial_count = int((universe_status.get("data_status") == "PARTIAL").sum()) if not universe_status.empty else 0
    signal_date_d = signal_dates.get("D") if signal_dates is not None else None
    signal_date_w = signal_dates.get("W") if signal_dates is not None else None
    signal_date_m = signal_dates.get("M") if signal_dates is not None else None
    overview = pd.DataFrame(
        [
            {"section": "report", "item": "generated_at", "value": now_shanghai().isoformat()},
            {"section": "report", "item": "signal_date", "value": signal_date.isoformat()},
            {"section": "report", "item": "signal_date_d", "value": signal_date_d.isoformat() if signal_date_d is not None else "NONE"},
            {"section": "report", "item": "signal_date_w", "value": signal_date_w.isoformat() if signal_date_w is not None else "NONE"},
            {"section": "report", "item": "signal_date_m", "value": signal_date_m.isoformat() if signal_date_m is not None else "NONE"},
            {"section": "report", "item": "intraday_ts", "value": intraday_ts.isoformat() if intraday_ts is not None else "NONE"},
            {"section": "report", "item": "symbol_count", "value": str(len(universe_status.index))},
            {"section": "report", "item": "gap_rows", "value": str(len(data_gaps.index))},
            {"section": "report", "item": "no_data_count", "value": str(no_data_count)},
            {"section": "report", "item": "partial_count", "value": str(partial_count)},
            {"section": "sheet", "item": "Data_Gaps", "value": "仅保留存在 NO_DATA / PARTIAL 的问题标的"},
            {"section": "sheet", "item": "Universe_Status", "value": "全量标的状态，用于排查覆盖范围与问题原因"},
            *_overview_count_rows(universe_status, "data_status", "data_status_count", DATA_GAP_STATUS_ORDER),
            *_overview_count_rows(universe_status, "missing_horizons", "missing_horizon_count", ["long_term", "short_term", "long_term,short_term", "NONE"]),
        ]
    )
    return {
        "Data_Gaps": data_gaps,
        "Universe_Status": universe_status,
        "Overview": overview,
    }


def _write_data_gap_workbook(output_path: Path, frames: dict[str, pd.DataFrame], engine: Literal["xlsxwriter"]) -> None:
    with pd.ExcelWriter(output_path, engine=engine) as writer:
        workbook = cast(Any, writer.book)
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
        for sheet_name, frame in frames.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = cast(Any, writer.sheets[sheet_name])
            _set_column_widths(worksheet, frame, max_width=42)
            worksheet.set_row(0, 22, header_format)
            if not frame.empty:
                worksheet.autofilter(0, 0, len(frame.index), len(frame.columns) - 1)
            if sheet_name in {"Data_Gaps", "Universe_Status"}:
                worksheet.freeze_panes(1, 6)
                action_indexes = [frame.columns.get_loc(column) for column in ACTION_COLUMNS if column in frame.columns and isinstance(frame.columns.get_loc(column), int)]
                for column_index in action_indexes:
                    if isinstance(column_index, int):
                        _apply_action_format(workbook, worksheet, 1, len(frame.index), column_index, column_index)
            else:
                worksheet.freeze_panes(1, 1)
            if sheet_name == "Data_Gaps":
                worksheet.activate()
                worksheet.set_first_sheet()


def export_data_gap_artifacts(
    frames: dict[str, pd.DataFrame],
    signal_date: date,
    intraday_ts: datetime | None,
    signal_dates: dict[str, date | None] | None = None,
    output_dir: str | Path = "reports/data_gaps",
) -> dict[str, Path]:
    engine = _resolve_excel_engine()
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = intraday_ts.strftime("%Y%m%d_%H%M") if intraday_ts is not None else signal_date.strftime("%Y%m%d")
    csv_path = folder / f"data_gaps_{suffix}.csv"
    status_csv_path = folder / f"data_gap_status_{suffix}.csv"
    json_path = folder / f"data_gaps_{suffix}.json"
    xlsx_path = folder / f"data_gaps_{suffix}.xlsx"

    data_gaps = frames["Data_Gaps"]
    universe_status = frames["Universe_Status"]
    signal_date_d = signal_dates.get("D") if signal_dates is not None else None
    signal_date_w = signal_dates.get("W") if signal_dates is not None else None
    signal_date_m = signal_dates.get("M") if signal_dates is not None else None
    data_gaps.to_csv(csv_path, index=False, encoding="utf-8-sig")
    universe_status.to_csv(status_csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(
            {
                "signal_date": signal_date.isoformat(),
                "signal_date_d": signal_date_d.isoformat() if signal_date_d is not None else None,
                "signal_date_w": signal_date_w.isoformat() if signal_date_w is not None else None,
                "signal_date_m": signal_date_m.isoformat() if signal_date_m is not None else None,
                "intraday_ts": intraday_ts.isoformat() if intraday_ts is not None else None,
                "rows": int(len(universe_status.index)),
                "gap_rows": int(len(data_gaps.index)),
                "records": data_gaps.to_dict(orient="records"),
                "universe_status": universe_status.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        _write_data_gap_workbook(output_path=xlsx_path, frames=frames, engine=engine)
    except PermissionError:
        fallback_suffix = now_shanghai().strftime("%Y%m%d_%H%M%S")
        xlsx_path = folder / f"data_gaps_{suffix}_{fallback_suffix}.xlsx"
        _write_data_gap_workbook(output_path=xlsx_path, frames=frames, engine=engine)
    return {
        "csv_path": csv_path,
        "status_csv_path": status_csv_path,
        "json_path": json_path,
        "xlsx_path": xlsx_path,
    }


def export_data_gap_report(
    signal_date: date | None = None,
    intraday_ts: datetime | None = None,
    intraday_bar_frequency: str = "5",
    output_dir: str | Path = "reports/data_gaps",
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
    daily_frames = build_daily_conclusion_frames(
        summary=cast(pd.DataFrame, context["summary"]),
        eod_d=cast(pd.DataFrame, context["eod_d"]),
        eod_w=cast(pd.DataFrame, context["eod_w"]),
        eod_m=cast(pd.DataFrame, context["eod_m"]),
        intraday=cast(pd.DataFrame, context["intraday"]),
        preclose=cast(pd.DataFrame, context["preclose"]),
        signal_date=cast(date, context["signal_date"]),
        intraday_ts=cast(datetime | None, context["intraday_ts"]),
        market_data_by_symbol=cast(dict[str, pd.DataFrame], context["market_data_by_symbol"]),
        fallback_symbols=universe_symbols,
    )
    frames = build_data_gap_report_frames(
        conclusion=cast(pd.DataFrame, daily_frames["Daily_Conclusion"]),
        signal_date=cast(date, context["signal_date"]),
        signal_dates=cast(dict[str, date | None], context["signal_dates"]),
        intraday_ts=cast(datetime | None, context["intraday_ts"]),
        market_data_by_symbol=cast(dict[str, pd.DataFrame], context["market_data_by_symbol"]),
    )
    signal_dates = cast(dict[str, date | None], context["signal_dates"])
    target_ts = cast(datetime | None, context["intraday_ts"])
    exports = export_data_gap_artifacts(
        frames=frames,
        signal_date=cast(date, context["signal_date"]),
        intraday_ts=target_ts,
        signal_dates=signal_dates,
        output_dir=output_dir,
    )
    universe_status = frames["Universe_Status"]
    data_gaps = frames["Data_Gaps"]
    target_date_d = signal_dates.get("D")
    target_date_w = signal_dates.get("W")
    target_date_m = signal_dates.get("M")
    return {
        "signal_date": cast(date, context["signal_date"]).isoformat(),
        "signal_date_d": target_date_d.isoformat() if target_date_d is not None else None,
        "signal_date_w": target_date_w.isoformat() if target_date_w is not None else None,
        "signal_date_m": target_date_m.isoformat() if target_date_m is not None else None,
        "intraday_ts": target_ts.isoformat() if target_ts is not None else None,
        "rows": int(len(universe_status.index)),
        "gap_rows": int(len(data_gaps.index)),
        "no_data_count": int((universe_status.get("data_status") == "NO_DATA").sum()) if not universe_status.empty else 0,
        "partial_count": int((universe_status.get("data_status") == "PARTIAL").sum()) if not universe_status.empty else 0,
        "sheet_names": list(frames.keys()),
        "csv_path": str(exports["csv_path"]),
        "status_csv_path": str(exports["status_csv_path"]),
        "json_path": str(exports["json_path"]),
        "xlsx_path": str(exports["xlsx_path"]),
    }
