from __future__ import annotations

from contextlib import contextmanager
import tempfile
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from web_ui.dashboard_service import (
    _build_market_overview_tables,
    _enrich_latest_intraday,
    _mark_stale_quote,
    _merge_preclose_fallback,
    _quote_runtime_context,
    _resolve_quote_row,
    _sort_quote_rows,
    _split_quote_rows,
    build_dashboard_snapshot,
    refresh_dashboard_snapshot,
)


class DashboardServiceTests(unittest.TestCase):
    def test_quote_runtime_context_uses_latest_closed_day_outside_session(self):
        runtime = type("Runtime", (), {
            "intraday_window_am_start": "09:30",
            "intraday_window_am_end": "11:30",
            "intraday_window_pm_start": "13:00",
            "intraday_window_pm_end": "15:00",
        })()

        use_live, closed_day = _quote_runtime_context(runtime, reference=datetime(2026, 3, 10, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

        self.assertFalse(use_live)
        self.assertEqual(str(closed_day), "2026-03-10")

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
            {"symbol": "159915", "change_pct": None, "quote_source": "无数据 / No Data", "asset_type": "ETF", "current_price": None},
            {"symbol": "159611", "change_pct": None, "quote_source": "旧盘中快照 / Stale Intraday", "asset_type": "ETF", "current_price": 1.157},
            {"symbol": "000852", "change_pct": 0.0},
        ]

        split = _split_quote_rows(rows)

        self.assertEqual([row["symbol"] for row in split["gainers"]], ["000905", "510300"])
        self.assertEqual([row["symbol"] for row in split["losers"]], ["000300"])
        self.assertEqual([row["symbol"] for row in split["flat"]], ["000852"])
        self.assertEqual([row["symbol"] for row in split["stale"]], ["159611"])
        self.assertEqual([row["symbol"] for row in split["missing"]], ["159915"])

    def test_merge_preclose_fallback_overrides_stale_intraday_quote(self):
        row = {
            "symbol": "510300",
            "current_price": 4.599,
            "prev_close": 4.667,
            "change_value": -0.068,
            "change_pct": -0.0146,
            "quote_source": "实时快照 / Intraday",
            "updated_at": "2026-03-09T11:05:00",
        }

        merged = _merge_preclose_fallback(
            row=row,
            asset_type="ETF",
            preclose_by_symbol={
                "510300": {
                    "latest_price": 4.712,
                    "prev_close": 4.667,
                    "day_change_pct": 0.0096,
                    "analysis_ts": "2026-03-10T14:50:12.378868+08:00",
                    "signal_date": "2026-03-10",
                }
            },
        )

        self.assertEqual(merged["current_price"], 4.712)
        self.assertEqual(merged["quote_source"], "预收盘快照 / Preclose Snapshot")
        self.assertEqual(merged["updated_at"], "2026-03-10T14:50:12.378868+08:00")

    def test_mark_stale_quote_relabels_old_intraday_source(self):
        stale = _mark_stale_quote(
            {
                "symbol": "159611",
                "quote_source": "实时快照 / Intraday",
                "updated_at": "2026-03-09T11:05:00",
            },
            reference_date=__import__("datetime").date(2026, 3, 10),
        )

        self.assertEqual(stale["quote_source"], "旧盘中快照 / Stale Intraday")

    def test_resolve_quote_row_prefers_daily_close_outside_session(self):
        row = _resolve_quote_row(
            symbol="000300",
            asset_type="INDEX",
            meta=None,
            daily_frame=__import__("pandas").DataFrame([
                {"date": "2026-03-05", "close": 4647.692},
                {"date": "2026-03-06", "close": 4660.439},
            ]),
            intraday_frame=__import__("pandas").DataFrame([
                {"date": "2026-03-10T14:50:12+08:00", "close": 4590.77},
            ]),
            preclose_by_symbol={
                "000300": {
                    "latest_price": 4590.77,
                    "prev_close": 4647.692,
                    "day_change_pct": -0.0122,
                    "analysis_ts": "2026-03-10T14:50:12+08:00",
                    "signal_date": "2026-03-10",
                }
            },
            use_live_quotes=False,
            reference_date=__import__("datetime").date(2026, 3, 10),
        )

        self.assertEqual(row["current_level"], 4660.439)
        self.assertEqual(row["prev_close"], 4647.692)
        self.assertEqual(row["quote_source"], "旧收盘价格 / Stale Daily Close")

    def test_resolve_quote_row_does_not_fall_back_to_daily_close_during_live_session_without_intraday(self):
        row = _resolve_quote_row(
            symbol="HSTECH",
            asset_type="INDEX",
            meta=None,
            daily_frame=__import__("pandas").DataFrame([
                {"date": "2026-03-05", "close": 4796.33},
                {"date": "2026-03-06", "close": 4947.5},
            ]),
            intraday_frame=__import__("pandas").DataFrame(),
            preclose_by_symbol={},
            use_live_quotes=True,
            reference_date=__import__("datetime").date(2026, 3, 11),
        )

        self.assertIsNone(row["current_level"])
        self.assertEqual(row["quote_source"], "无数据 / No Data")

    def test_enrich_latest_intraday_adds_name_from_symbol_meta(self):
        latest_intraday = __import__("pandas").DataFrame([
            {"symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY", "ts": "2026-03-10T10:16:29+08:00"}
        ])

        enriched = _enrich_latest_intraday(latest_intraday, __import__("pandas").DataFrame())

        self.assertEqual(enriched.iloc[0]["name"], "沪深300ETF")

    def test_build_market_overview_tables_fetches_live_quote_bars_when_db_bars_are_stale(self):
        runtime = type(
            "Runtime",
            (),
            {
                "intraday_bar_frequency": "5",
                "intraday_window_am_start": "09:30",
                "intraday_window_am_end": "11:30",
                "intraday_window_pm_start": "13:00",
                "intraday_window_pm_end": "15:00",
            },
        )()
        universe = type("Universe", (), {"index_symbols": ["000001"], "etf_symbols": ["510300"]})()

        @contextmanager
        def fake_session_scope():
            yield object()

        stale_intraday = {
            "000001": __import__("pandas").DataFrame([{"date": "2026-03-09T11:05:00", "close": 4084.567}]),
            "510300": __import__("pandas").DataFrame([{"date": "2026-03-09T11:05:00", "close": 4.629}]),
        }
        fresh_intraday = {
            "000001": __import__("pandas").DataFrame([{"date": "2026-03-11T14:10:00", "close": 4123.138}]),
            "510300": __import__("pandas").DataFrame([{"date": "2026-03-11T14:10:00", "close": 4.683}]),
        }

        with patch("web_ui.dashboard_service.load_runtime_config", return_value=runtime), patch(
            "web_ui.dashboard_service.load_universe_config", return_value=universe
        ), patch("web_ui.dashboard_service.load_symbol_meta_map", return_value={}), patch(
            "web_ui.dashboard_service.now_shanghai",
            return_value=datetime(2026, 3, 11, 14, 11, tzinfo=ZoneInfo("Asia/Shanghai")),
        ), patch("web_ui.dashboard_service.is_trading_session", return_value=True), patch(
            "web_ui.dashboard_service.latest_closed_trading_date", return_value=__import__("datetime").date(2026, 3, 10)
        ), patch("web_ui.dashboard_service.session_scope", fake_session_scope), patch(
            "web_ui.dashboard_service.load_market_prices_map",
            return_value={
                "000001": __import__("pandas").DataFrame([{"date": "2026-03-10", "close": 4123.138}, {"date": "2026-03-09", "close": 4096.602}]),
                "510300": __import__("pandas").DataFrame([{"date": "2026-03-10", "close": 4.683}, {"date": "2026-03-09", "close": 4.629}]),
            },
        ), patch(
            "web_ui.dashboard_service.load_realtime_bars_map",
            side_effect=[stale_intraday, fresh_intraday],
        ), patch(
            "web_ui.dashboard_service._fetch_live_quote_bars",
            return_value=fresh_intraday,
        ) as mock_fetch_live_quote_bars:
            result = _build_market_overview_tables(preclose=__import__("pandas").DataFrame())

        mock_fetch_live_quote_bars.assert_called_once()
        self.assertEqual(result["index_quotes"][0]["current_level"], 4123.138)

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
            "index_quote_stale": [],
            "index_quote_missing": [],
            "etf_quote_gainers": [{"symbol": "510300", "name": "沪深300ETF", "current_price": 4.5231, "change_value": 0.0363, "change_pct": 0.0081}],
            "etf_quote_losers": [],
            "etf_quote_flat": [],
            "etf_quote_stale": [],
            "etf_quote_missing": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "web_ui.dashboard_service._build_market_overview_tables",
            return_value=market_overview,
        ):
            report_root = Path(temp_dir) / "reports"
            (report_root / "summary").mkdir(parents=True)
            (report_root / "intraday").mkdir(parents=True)
            (report_root / "preclose").mkdir(parents=True)
            (report_root / "daily_conclusion").mkdir(parents=True)

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
            (report_root / "daily_conclusion" / "daily_conclusion_20260309.csv").write_text(
                "conviction_rank,symbol,name,overall_action,hypothesis_consensus_action,hypothesis_tiebreak_applied,hypothesis_summary_text\n"
                "1,510300,沪深300ETF,BUY,BUY,True,分组共识改判为 BUY（2 组；趋势跟随@long_term | 动量@short_term）\n"
                "2,000300,沪深300,HOLD,SELL,False,分组共识偏向 SELL（2 组；均值回归@short_term | 趋势跟随@long_term）\n",
                encoding="utf-8-sig",
            )

            snapshot = build_dashboard_snapshot(report_root=report_root)

        self.assertEqual(snapshot["metrics"]["summary_rows"], 2)
        self.assertEqual(snapshot["metrics"]["intraday_signal_rows"], 1)
        self.assertEqual(snapshot["metrics"]["index_quote_rows"], 1)
        self.assertEqual(snapshot["metrics"]["etf_quote_rows"], 1)
        self.assertEqual(snapshot["metrics"]["hypothesis_focus_rows"], 2)
        self.assertEqual(snapshot["metrics"]["active_intraday_count"], 1)
        self.assertEqual(snapshot["metrics"]["priority_action_count"], 1)
        self.assertEqual(len(snapshot["tables"]["action_focus"]), 1)
        self.assertEqual(snapshot["tables"]["hypothesis_focus"][0]["symbol"], "510300")
        self.assertIn("分组共识", snapshot["tables"]["hypothesis_focus"][0]["hypothesis_summary_text"])
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
            "index_quote_stale": [],
            "index_quote_missing": [],
            "etf_quote_gainers": [],
            "etf_quote_losers": [],
            "etf_quote_flat": [],
            "etf_quote_stale": [],
            "etf_quote_missing": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "web_ui.dashboard_service._build_market_overview_tables",
            return_value=market_overview,
        ):
            report_root = Path(temp_dir) / "reports"
            (report_root / "summary").mkdir(parents=True)
            (report_root / "intraday").mkdir(parents=True)
            (report_root / "daily_conclusion").mkdir(parents=True)
            (report_root / "summary" / "signal_summary_20260309_1102.csv").write_text(
                "conviction_rank,symbol,name,intraday,dashboard_action,composite_score\n"
                "1,510300,沪深300ETF,BUY,PRIORITY_BUY,7.0\n",
                encoding="utf-8-sig",
            )
            (report_root / "daily_conclusion" / "daily_conclusion_20260309.csv").write_text(
                "conviction_rank,symbol,name,overall_action,hypothesis_consensus_action,hypothesis_tiebreak_applied,hypothesis_summary_text\n"
                "1,510300,沪深300ETF,BUY,BUY,True,分组共识改判为 BUY（2 组；趋势跟随@long_term | 动量@short_term）\n",
                encoding="utf-8-sig",
            )

            with patch("scheduler.intraday_runner.run_intraday_iteration", return_value={"bar_rows": 2280, "signal_rows": 209}), patch(
                "core.clock.now_shanghai",
                return_value=datetime(2026, 3, 9, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai")),
            ), patch(
                "signal_service.daily_conclusion_report.export_daily_conclusion_report",
                return_value={"csv_path": str(report_root / "daily_conclusion" / "daily_conclusion_20260309_1450.csv")},
            ):
                snapshot = refresh_dashboard_snapshot(report_root=report_root)

        self.assertEqual(snapshot["refresh_result"]["bar_rows"], 2280)
        self.assertIn("daily_conclusion_result", snapshot["refresh_result"])
        self.assertEqual(snapshot["metrics"]["summary_rows"], 1)
        self.assertEqual(snapshot["metrics"]["hypothesis_focus_rows"], 1)


if __name__ == "__main__":
    unittest.main()
