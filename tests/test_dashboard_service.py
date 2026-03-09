from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from web_ui.dashboard_service import build_dashboard_snapshot, refresh_dashboard_snapshot, _sort_quote_rows, _split_quote_rows


class DashboardServiceTests(unittest.TestCase):
    def test_sort_quote_rows_orders_by_change_pct_descending_and_places_missing_last(self):
        rows = [
            {"symbol": "510300", "change_pct": 0.012, "change_value": 0.05},
            {"symbol": "159915", "change_pct": None, "change_value": None},
            {"symbol": "000300", "change_pct": -0.023, "change_value": -88.5},
            {"symbol": "000905", "change_pct": 0.034, "change_value": 120.1},
        ]

        ordered = _sort_quote_rows(rows)

        self.assertEqual([row["symbol"] for row in ordered], ["000905", "510300", "000300", "159915"])

    def test_split_quote_rows_separates_gainers_losers_and_flat(self):
        rows = [
            {"symbol": "000905", "change_pct": 0.034},
            {"symbol": "510300", "change_pct": 0.012},
            {"symbol": "000300", "change_pct": -0.023},
            {"symbol": "159915", "change_pct": None},
            {"symbol": "000852", "change_pct": 0.0},
        ]

        split = _split_quote_rows(rows)

        self.assertEqual([row["symbol"] for row in split["gainers"]], ["000905", "510300"])
        self.assertEqual([row["symbol"] for row in split["losers"]], ["000300"])
        self.assertEqual([row["symbol"] for row in split["flat"]], ["000852", "159915"])

    def test_build_dashboard_snapshot_reads_latest_reports(self):
        market_overview = {
            "quote_status": "实时数据库 / Live DB",
            "quote_error": None,
            "quote_bar_frequency": "5",
            "index_quotes": [{"symbol": "000300", "name": "沪深300", "current_level": 3812.12, "change_value": 46.21, "change_pct": 0.0123}],
            "etf_quotes": [{"symbol": "510300", "name": "沪深300ETF", "current_price": 4.5231, "change_value": 0.0363, "change_pct": 0.0081}],
            "index_quote_gainers": [{"symbol": "000300", "name": "沪深300", "current_level": 3812.12, "change_value": 46.21, "change_pct": 0.0123}],
            "index_quote_losers": [],
            "index_quote_flat": [],
            "etf_quote_gainers": [{"symbol": "510300", "name": "沪深300ETF", "current_price": 4.5231, "change_value": 0.0363, "change_pct": 0.0081}],
            "etf_quote_losers": [],
            "etf_quote_flat": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "web_ui.dashboard_service._build_market_overview_tables",
            return_value=market_overview,
        ):
            report_root = Path(temp_dir) / "reports"
            (report_root / "summary").mkdir(parents=True)
            (report_root / "intraday").mkdir(parents=True)
            (report_root / "preclose").mkdir(parents=True)

            (report_root / "summary" / "signal_summary_20260309_1030.csv").write_text(
                "conviction_rank,symbol,name,intraday,dashboard_action,composite_score\n"
                "1,510300,沪深300ETF,BUY,PRIORITY_BUY,6.5\n"
                "2,159915,创业板ETF,HOLD,NEUTRAL,0.1\n",
                encoding="utf-8-sig",
            )
            (report_root / "summary" / "signal_push_candidates_20260309_1030.csv").write_text(
                "push_rank,symbol,name,dashboard_action,change_reason,composite_score,review_gate\n"
                "1,510300,沪深300ETF,PRIORITY_BUY,NEW_ENTRY,6.5,CONFIRM\n",
                encoding="utf-8-sig",
            )
            (report_root / "summary" / "signal_top_candidates_20260309_1030.csv").write_text(
                "direction,symbol,name,dashboard_action\nBUY,510300,沪深300ETF,PRIORITY_BUY\n",
                encoding="utf-8-sig",
            )
            (report_root / "summary" / "signal_group_summary_20260309_1030.csv").write_text(
                "bucket,asset_type,count,avg_composite_score\n宽基ETF,ETF,2,3.3\n",
                encoding="utf-8-sig",
            )
            (report_root / "intraday" / "signals_5m_20260309_1030.csv").write_text(
                "ts,symbol,strategy,signal,score\n"
                "2026-03-09T10:30:00+08:00,510300,EMA_cross_strategy,BUY,1.2\n",
                encoding="utf-8-sig",
            )
            (report_root / "preclose" / "preclose_decision_20260309.csv").write_text(
                "symbol,decision_signal\n510300,BUY\n",
                encoding="utf-8-sig",
            )

            snapshot = build_dashboard_snapshot(report_root=report_root)

        self.assertEqual(snapshot["metrics"]["summary_rows"], 2)
        self.assertEqual(snapshot["metrics"]["intraday_signal_rows"], 1)
        self.assertEqual(snapshot["metrics"]["index_quote_rows"], 1)
        self.assertEqual(snapshot["metrics"]["etf_quote_rows"], 1)
        self.assertEqual(snapshot["metrics"]["active_intraday_count"], 1)
        self.assertEqual(snapshot["metrics"]["priority_action_count"], 1)
        self.assertEqual(len(snapshot["tables"]["action_focus"]), 1)
        self.assertEqual(snapshot["tables"]["action_focus"][0]["symbol"], "510300")
        self.assertEqual(snapshot["tables"]["index_quotes"][0]["symbol"], "000300")
        self.assertEqual(snapshot["tables"]["etf_quotes"][0]["symbol"], "510300")
        self.assertEqual(snapshot["tables"]["index_quotes"][0]["change_value"], 46.21)
        self.assertEqual(snapshot["tables"]["index_quote_gainers"][0]["symbol"], "000300")
        self.assertEqual(snapshot["tables"]["etf_quote_gainers"][0]["symbol"], "510300")
        self.assertTrue(snapshot["latest_files"]["summary_path"].endswith("signal_summary_20260309_1030.csv"))

    def test_refresh_dashboard_snapshot_includes_refresh_result(self):
        market_overview = {
            "quote_status": "实时数据库 / Live DB",
            "quote_error": None,
            "quote_bar_frequency": "5",
            "index_quotes": [],
            "etf_quotes": [],
            "index_quote_gainers": [],
            "index_quote_losers": [],
            "index_quote_flat": [],
            "etf_quote_gainers": [],
            "etf_quote_losers": [],
            "etf_quote_flat": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "web_ui.dashboard_service._build_market_overview_tables",
            return_value=market_overview,
        ):
            report_root = Path(temp_dir) / "reports"
            (report_root / "summary").mkdir(parents=True)
            (report_root / "intraday").mkdir(parents=True)
            (report_root / "summary" / "signal_summary_20260309_1102.csv").write_text(
                "conviction_rank,symbol,name,intraday,dashboard_action,composite_score\n"
                "1,510300,沪深300ETF,BUY,PRIORITY_BUY,7.0\n",
                encoding="utf-8-sig",
            )

            with patch("scheduler.intraday_runner.run_intraday_iteration", return_value={"bar_rows": 2280, "signal_rows": 209}):
                snapshot = refresh_dashboard_snapshot(report_root=report_root)

        self.assertEqual(snapshot["refresh_result"]["bar_rows"], 2280)
        self.assertEqual(snapshot["metrics"]["summary_rows"], 1)


if __name__ == "__main__":
    unittest.main()
