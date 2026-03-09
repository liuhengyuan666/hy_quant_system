from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from xml.etree import ElementTree

import pandas as pd

from signal_service.daily_conclusion_report import (
    build_operation_view,
    build_daily_conclusion_frames,
    build_daily_conclusions,
    export_daily_conclusion_artifacts,
)


class DailyConclusionReportTests(unittest.TestCase):
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
                    "dashboard_action": "PRIORITY_BUY",
                    "eod_bias": "BUY",
                    "alignment": "ALIGNED",
                },
                {
                    "conviction_rank": 2,
                    "symbol": "000300",
                    "display_symbol": "1A0300",
                    "name": "沪深300",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "dashboard_action": "TREND_SELL",
                    "eod_bias": "SELL",
                    "alignment": "NEUTRAL",
                },
                {
                    "conviction_rank": 3,
                    "symbol": "159611",
                    "display_symbol": "E159611",
                    "name": "电力ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                    "dashboard_action": "WATCHLIST",
                    "eod_bias": "HOLD",
                    "alignment": "NEUTRAL",
                },
            ]
        )

    def test_build_daily_conclusions_outputs_long_and_short_actions(self):
        summary = self._summary()
        eod_d = pd.DataFrame(
            [
                {"date": "2026-03-10", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-10", "symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY"},
                {"date": "2026-03-10", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                {"date": "2026-03-10", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                {"date": "2026-03-10", "symbol": "510300", "strategy": "ADX_trend_strategy", "signal": "BUY"},
                {"date": "2026-03-10", "symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
                {"date": "2026-03-10", "symbol": "000300", "strategy": "EMA_cross_strategy", "signal": "SELL"},
                {"date": "2026-03-10", "symbol": "000300", "strategy": "Momentum_20_strategy", "signal": "HOLD"},
                {"date": "2026-03-10", "symbol": "000300", "strategy": "RSRS_strategy", "signal": "SELL"},
                {"date": "2026-03-10", "symbol": "000300", "strategy": "ADX_trend_strategy", "signal": "SELL"},
            ]
        )
        eod_w = pd.DataFrame(
            [
                {"date": "2026-03-07", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "510300", "strategy": "Triple_MA_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "000300", "strategy": "RSRS_strategy", "signal": "SELL"},
                {"date": "2026-03-07", "symbol": "000300", "strategy": "Triple_MA_strategy", "signal": "SELL"},
            ]
        )
        eod_m = pd.DataFrame(
            [
                {"date": "2026-03-07", "symbol": "510300", "strategy": "Momentum_60_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "510300", "strategy": "ETF_rotation_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "000300", "strategy": "Momentum_60_strategy", "signal": "SELL"},
            ]
        )
        intraday = pd.DataFrame(
            [
                {"ts": "2026-03-10T14:45:00+08:00", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                {"ts": "2026-03-10T14:45:00+08:00", "symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY"},
                {"ts": "2026-03-10T14:45:00+08:00", "symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )
        preclose = pd.DataFrame(
            [
                {"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.8},
                {"symbol": "000300", "decision_signal": "SELL", "decision_score": -4.1},
            ]
        )
        market_data_by_symbol = {
            "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
            "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}]),
            "159611": pd.DataFrame(),
        }

        conclusion, long_term_evidence, short_term_evidence, data_gaps = build_daily_conclusions(
            summary=summary,
            eod_d=eod_d,
            eod_w=eod_w,
            eod_m=eod_m,
            intraday=intraday,
            preclose=preclose,
            market_data_by_symbol=market_data_by_symbol,
        )

        etf_row = conclusion[conclusion["symbol"] == "510300"].iloc[0]
        index_row = conclusion[conclusion["symbol"] == "000300"].iloc[0]
        no_data_row = conclusion[conclusion["symbol"] == "159611"].iloc[0]

        self.assertEqual(etf_row["long_term_action"], "BUY")
        self.assertEqual(etf_row["short_term_action"], "BUY")
        self.assertEqual(etf_row["preclose_signal"], "BUY")
        self.assertEqual(etf_row["overall_action"], "BUY")
        self.assertEqual(index_row["long_term_action"], "SELL")
        self.assertEqual(index_row["short_term_action"], "SELL")
        self.assertEqual(no_data_row["data_status"], "NO_DATA")
        self.assertEqual(no_data_row["long_term_action"], "NO_DATA")
        self.assertEqual(no_data_row["short_term_action"], "NO_DATA")
        self.assertTrue((long_term_evidence["horizon"] == "long_term").all())
        self.assertTrue((short_term_evidence["horizon"] == "short_term").all())
        self.assertEqual(data_gaps[data_gaps["symbol"] == "159611"].iloc[0]["issue_type"], "NO_DATA")

    def test_build_operation_view_creates_concise_action_sheet(self):
        conclusion = pd.DataFrame(
            [
                {
                    "conviction_rank": 1,
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "long_term_action": "BUY",
                    "short_term_action": "BUY",
                    "preclose_signal": "BUY",
                    "overall_action": "BUY",
                    "data_status": "OK",
                },
                {
                    "conviction_rank": 4,
                    "symbol": "513130",
                    "display_symbol": "E513130",
                    "name": "恒生科技ETF",
                    "asset_type": "ETF",
                    "bucket": "港股",
                    "long_term_action": "SELL",
                    "short_term_action": "SELL",
                    "preclose_signal": "SELL",
                    "overall_action": "SELL",
                    "data_status": "OK",
                },
                {
                    "conviction_rank": 5,
                    "symbol": "000001",
                    "display_symbol": "1A0001",
                    "name": "上证指数",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "long_term_action": "BUY",
                    "short_term_action": "HOLD",
                    "preclose_signal": "HOLD",
                    "overall_action": "BUY",
                    "data_status": "OK",
                },
                {
                    "conviction_rank": 2,
                    "symbol": "000300",
                    "display_symbol": "1A0300",
                    "name": "沪深300",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "long_term_action": "BUY",
                    "short_term_action": "SELL",
                    "preclose_signal": "HOLD",
                    "overall_action": "HOLD",
                    "data_status": "OK",
                },
                {
                    "conviction_rank": 6,
                    "symbol": "399006",
                    "display_symbol": "1A39006",
                    "name": "创业板指",
                    "asset_type": "INDEX",
                    "bucket": "宽基指数",
                    "long_term_action": "HOLD",
                    "short_term_action": "HOLD",
                    "preclose_signal": "BUY",
                    "overall_action": "HOLD",
                    "data_status": "OK",
                },
                {
                    "conviction_rank": 3,
                    "symbol": "159611",
                    "display_symbol": "E159611",
                    "name": "电力ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                    "long_term_action": "NO_DATA",
                    "short_term_action": "NO_DATA",
                    "preclose_signal": "HOLD",
                    "overall_action": "NO_DATA",
                    "data_status": "NO_DATA",
                },
            ]
        )

        operation_view = build_operation_view(conclusion)

        self.assertEqual(operation_view.iloc[0]["symbol"], "510300")
        self.assertEqual(operation_view.iloc[1]["symbol"], "513130")
        self.assertEqual(operation_view.iloc[2]["symbol"], "000001")
        self.assertEqual(operation_view.iloc[3]["symbol"], "000300")
        self.assertEqual(operation_view.iloc[4]["symbol"], "399006")
        self.assertEqual(operation_view.iloc[5]["symbol"], "159611")
        self.assertEqual(operation_view[operation_view["symbol"] == "510300"].iloc[0]["action_note"], "长短线同向看多")
        self.assertEqual(operation_view[operation_view["symbol"] == "000300"].iloc[0]["action_note"], "长短线分歧，谨慎处理")
        self.assertEqual(operation_view[operation_view["symbol"] == "399006"].iloc[0]["action_note"], "收盘前提示 BUY，但主结论仍观望")
        self.assertEqual(operation_view[operation_view["symbol"] == "159611"].iloc[0]["action_note"], "缺少历史行情，暂不判断")

    def test_export_daily_conclusion_artifacts_writes_workbook(self):
        summary = self._summary().head(2)
        frames = build_daily_conclusion_frames(
            summary=summary,
            eod_d=pd.DataFrame([{"date": "2026-03-10", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"}]),
            eod_w=pd.DataFrame(),
            eod_m=pd.DataFrame(),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame([{"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.5}]),
            signal_date=date(2026, 3, 10),
            intraday_ts=None,
            market_data_by_symbol={
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}]),
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            exported = export_daily_conclusion_artifacts(frames, signal_date=date(2026, 3, 10), intraday_ts=None, output_dir=temp_dir)
            self.assertTrue(exported["csv_path"].exists())
            self.assertTrue(exported["operation_csv_path"].exists())
            self.assertTrue(exported["json_path"].exists())
            self.assertTrue(exported["xlsx_path"].exists())
            with zipfile.ZipFile(exported["xlsx_path"], "r") as archive:
                workbook_xml = archive.read("xl/workbook.xml")
            root = ElementTree.fromstring(workbook_xml)
            namespace = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            sheet_names = [sheet.attrib.get("name", "") for sheet in root.findall("ns:sheets/ns:sheet", namespace)]

        self.assertIn("Operation_View", sheet_names)
        self.assertIn("Daily_Conclusion", sheet_names)
        self.assertIn("LongTerm_Evidence", sheet_names)
        self.assertIn("ShortTerm_Evidence", sheet_names)
        self.assertIn("Data_Gaps", sheet_names)
        self.assertEqual(sheet_names[0], "Operation_View")

    def test_build_daily_conclusion_frames_adds_action_breakdown_to_overview(self):
        summary = self._summary().head(2)
        frames = build_daily_conclusion_frames(
            summary=summary,
            eod_d=pd.DataFrame(
                [
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "000300", "strategy": "RSRS_strategy", "signal": "SELL"},
                ]
            ),
            eod_w=pd.DataFrame(),
            eod_m=pd.DataFrame(),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame(
                [
                    {"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.5},
                    {"symbol": "000300", "decision_signal": "SELL", "decision_score": -4.5},
                ]
            ),
            signal_date=date(2026, 3, 10),
            intraday_ts=None,
            market_data_by_symbol={
                "510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]),
                "000300": pd.DataFrame([{"date": "2026-03-10", "close": 3800.0}]),
            },
        )

        overview = frames["Overview"]
        overall_counts = overview[overview["section"] == "overall_action_count"].set_index("item")["value"].to_dict()
        long_term_counts = overview[overview["section"] == "long_term_action_count"].set_index("item")["value"].to_dict()
        short_term_counts = overview[overview["section"] == "short_term_action_count"].set_index("item")["value"].to_dict()
        preclose_counts = overview[overview["section"] == "preclose_signal_count"].set_index("item")["value"].to_dict()

        self.assertEqual(overall_counts["BUY"], "1")
        self.assertEqual(overall_counts["SELL"], "1")
        self.assertEqual(long_term_counts["BUY"], "1")
        self.assertEqual(long_term_counts["SELL"], "1")
        self.assertEqual(short_term_counts["BUY"], "1")
        self.assertEqual(short_term_counts["SELL"], "1")
        self.assertEqual(preclose_counts["BUY"], "1")
        self.assertEqual(preclose_counts["SELL"], "1")


if __name__ == "__main__":
    unittest.main()
