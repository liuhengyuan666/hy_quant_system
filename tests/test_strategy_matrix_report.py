from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pandas as pd

from signal_service.strategy_matrix_report import (
    build_strategy_report_frames,
    build_strategy_signal_matrix,
    build_strategy_statistics,
    export_strategy_matrix_workbook,
)


class StrategyMatrixReportTests(unittest.TestCase):
    def _summary(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "eod_d": "BUY",
                    "eod_w": "BUY",
                    "eod_m": "HOLD",
                    "intraday": "BUY",
                    "eod_bias": "BUY",
                    "alignment": "ALIGNED",
                    "secondary_action": "BUY_CONFIRM",
                    "secondary_confidence": 90.0,
                    "review_gate": "CONFIRM",
                    "review_score": 85.0,
                    "composite_score": 6.2,
                    "dashboard_action": "PRIORITY_BUY",
                },
                {
                    "conviction_rank": 2,
                    "symbol": "000300",
                    "display_symbol": "1A0300",
                    "name": "沪深300",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "eod_d": "SELL",
                    "eod_w": "HOLD",
                    "eod_m": "SELL",
                    "intraday": "HOLD",
                    "eod_bias": "SELL",
                    "alignment": "NEUTRAL",
                    "secondary_action": "HOLD_OBSERVE",
                    "secondary_confidence": 55.0,
                    "review_gate": "CAUTION",
                    "review_score": 60.0,
                    "composite_score": -2.5,
                    "dashboard_action": "TREND_SELL",
                },
            ]
        )

    def test_build_strategy_signal_matrix_marks_na_and_not_run(self):
        summary = self._summary()
        eod_signals = pd.DataFrame(
            [
                {"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"symbol": "510300", "strategy": "ETF_rotation_strategy", "signal": "SELL"},
                {"symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )
        intraday_signals = pd.DataFrame(
            [
                {"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )

        eod_matrix = build_strategy_signal_matrix(summary, eod_signals, supported_mode="eod")
        intraday_matrix = build_strategy_signal_matrix(summary, intraday_signals, supported_mode="intraday")

        etf_row = eod_matrix[eod_matrix["symbol"] == "510300"].iloc[0]
        index_row = eod_matrix[eod_matrix["symbol"] == "000300"].iloc[0]
        intraday_row = intraday_matrix[intraday_matrix["symbol"] == "510300"].iloc[0]

        self.assertEqual(etf_row["MA_strategy"], "BUY")
        self.assertEqual(etf_row["ETF_rotation_strategy"], "SELL")
        self.assertEqual(index_row["ETF_rotation_strategy"], "N/A")
        self.assertEqual(intraday_row["RSRS_strategy"], "NOT_RUN")

    def test_build_strategy_signal_matrix_marks_no_data_symbols(self):
        summary = pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "159611",
                    "display_symbol": "E159611",
                    "name": "电力ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                }
            ]
        )

        matrix = build_strategy_signal_matrix(
            summary,
            pd.DataFrame(),
            supported_mode="eod",
            no_data_symbols={"159611"},
        )

        row = matrix.iloc[0]
        self.assertEqual(row["MA_strategy"], "NO_DATA")
        self.assertEqual(row["ETF_rotation_strategy"], "NO_DATA")

    def test_build_strategy_report_frames_adds_action_focus_and_groups_by_asset_type(self):
        summary = self._summary()
        eod_signals = pd.DataFrame(
            [
                {"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )
        preclose = pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "decision_signal": "BUY",
                    "decision_score": 4.5,
                    "dashboard_action": "PRIORITY_BUY",
                },
                {
                    "conviction_rank": 2,
                    "symbol": "000300",
                    "display_symbol": "1A0300",
                    "name": "沪深300",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "decision_signal": "HOLD",
                    "decision_score": 1.0,
                    "dashboard_action": "TREND_SELL",
                },
            ]
        )

        frames = build_strategy_report_frames(
            summary=summary,
            eod_d=eod_signals,
            eod_w=eod_signals,
            eod_m=eod_signals,
            intraday=pd.DataFrame(),
            preclose=preclose,
            signal_date=date(2026, 3, 10),
            intraday_ts=None,
            market_data_by_symbol={
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}]),
            },
        )

        focus = frames["Action_Focus"]
        self.assertIn("Action_Focus", frames)
        self.assertEqual(focus.iloc[0]["symbol"], "000300")
        self.assertEqual(focus.iloc[1]["symbol"], "510300")
        self.assertEqual(focus[focus["symbol"] == "000300"].iloc[0]["eod_d_active"], "MA_strategy=SELL")
        self.assertEqual(focus[focus["symbol"] == "510300"].iloc[0]["preclose_signal"], "BUY")

    def test_build_strategy_report_frames_includes_fallback_universe_symbols(self):
        summary = self._summary().head(1)
        frames = build_strategy_report_frames(
            summary=summary,
            eod_d=pd.DataFrame([{"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"}]),
            eod_w=pd.DataFrame(),
            eod_m=pd.DataFrame(),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame(
                [
                    {"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.5},
                    {"symbol": "HSAHP", "decision_signal": "HOLD", "decision_score": 0.0},
                ]
            ),
            signal_date=date(2026, 3, 10),
            intraday_ts=None,
            market_data_by_symbol={
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
                "HSAHP": pd.DataFrame(),
            },
            fallback_symbols=["510300", "HSAHP"],
        )

        matrix_row = frames["EOD_D_Matrix"][frames["EOD_D_Matrix"]["symbol"] == "HSAHP"].iloc[0]
        summary_row = frames["Symbol_Summary"][frames["Symbol_Summary"]["symbol"] == "HSAHP"].iloc[0]
        preclose_row = frames["PRE_CLOSE_View"][frames["PRE_CLOSE_View"]["symbol"] == "HSAHP"].iloc[0]

        self.assertEqual(matrix_row["MA_strategy"], "NO_DATA")
        self.assertEqual(summary_row["eod_d"], "NO_DATA")
        self.assertEqual(preclose_row["decision_signal"], "HOLD")

    def test_build_strategy_statistics_counts_signal_states(self):
        summary = self._summary()
        matrix = build_strategy_signal_matrix(
            summary,
            pd.DataFrame(
                [
                    {"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                    {"symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
                ]
            ),
            supported_mode="eod",
        )
        stats = build_strategy_statistics({"EOD_D_Matrix": matrix})
        ma_stats = stats[stats["strategy"] == "MA_strategy"].iloc[0]

        self.assertEqual(int(ma_stats["buy_count"]), 1)
        self.assertEqual(int(ma_stats["sell_count"]), 1)
        self.assertEqual(int(ma_stats["active_signal_count"]), 2)

    def test_export_strategy_matrix_workbook_writes_expected_sheets(self):
        summary = self._summary()
        eod_signals = pd.DataFrame(
            [
                {"symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )
        preclose = pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "decision_signal": "BUY",
                    "decision_score": 4.5,
                    "decision_reason": "trend_supports_buy",
                    "trend_state": "UPTREND",
                    "latest_price": 4.56,
                    "day_change_pct": 0.01,
                    "distance_to_ma20_pct": 0.02,
                    "eod_bias": "BUY",
                    "alignment": "ALIGNED",
                    "secondary_action": "BUY_CONFIRM",
                    "secondary_confidence": 90.0,
                    "review_gate": "CONFIRM",
                    "dashboard_action": "PRIORITY_BUY",
                }
            ]
        )
        frames = build_strategy_report_frames(
            summary=summary,
            eod_d=eod_signals,
            eod_w=eod_signals,
            eod_m=eod_signals,
            intraday=pd.DataFrame(),
            preclose=preclose,
            signal_date=date(2026, 3, 10),
            intraday_ts=None,
            market_data_by_symbol={
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}]),
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = export_strategy_matrix_workbook(frames, signal_date=date(2026, 3, 10), intraday_ts=None, output_dir=temp_dir)
            self.assertTrue(workbook_path.exists())
            with zipfile.ZipFile(workbook_path, "r") as archive:
                workbook_xml = archive.read("xl/workbook.xml")
            root = ElementTree.fromstring(workbook_xml)
            namespace = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_names = [sheet.attrib.get("name", "") for sheet in root.findall("ns:sheets/ns:sheet", namespace)]

        self.assertIn("Overview", sheet_names)
        self.assertIn("Action_Focus", sheet_names)
        self.assertIn("EOD_D_Matrix", sheet_names)
        self.assertIn("PRE_CLOSE_View", sheet_names)

    @patch("signal_service.strategy_matrix_report._write_strategy_matrix_workbook")
    def test_export_strategy_matrix_workbook_falls_back_when_primary_locked(self, mock_write_workbook):
        mock_write_workbook.side_effect = [PermissionError("locked"), None]

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_strategy_matrix_workbook(
                frames={"Overview": pd.DataFrame([{"section": "report", "item": "signal_date", "value": "2026-03-10"}])},
                signal_date=date(2026, 3, 10),
                intraday_ts=None,
                output_dir=temp_dir,
            )

        self.assertEqual(mock_write_workbook.call_count, 2)
        self.assertIn("strategy_matrix_20260310_", result.name)


if __name__ == "__main__":
    unittest.main()
