from __future__ import annotations

from contextlib import contextmanager
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import pandas as pd
from unittest.mock import ANY, patch

from config.settings import RuntimeConfig
from signal_service.daily_conclusion_report import (
    _resolve_overall_action_with_hypothesis,
    build_operation_view,
    build_daily_conclusion_frames,
    build_daily_conclusions,
    export_daily_conclusion_artifacts,
    load_daily_conclusion_context,
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
        self.assertIn("分组共识", etf_row["hypothesis_summary_text"])
        self.assertEqual(index_row["long_term_action"], "SELL")
        self.assertEqual(index_row["short_term_action"], "SELL")
        self.assertEqual(no_data_row["data_status"], "NO_DATA")
        self.assertEqual(no_data_row["long_term_action"], "NO_DATA")
        self.assertEqual(no_data_row["short_term_action"], "NO_DATA")
        self.assertTrue((long_term_evidence["horizon"] == "long_term").all())
        self.assertTrue((short_term_evidence["horizon"] == "short_term").all())
        self.assertEqual(data_gaps[data_gaps["symbol"] == "159611"].iloc[0]["issue_type"], "NO_DATA")

    def test_build_daily_conclusions_uses_hypothesis_consensus_to_break_conflict(self):
        summary = self._summary().head(1)
        conclusion, _, _, _ = build_daily_conclusions(
            summary=summary,
            eod_d=pd.DataFrame(
                [
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "RSI_reversion_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Bollinger_reversion_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                ]
            ),
            eod_w=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "Triple_MA_strategy", "signal": "BUY"},
                ]
            ),
            eod_m=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "Momentum_60_strategy", "signal": "BUY"},
                ]
            ),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame([{"symbol": "510300", "decision_signal": "HOLD", "decision_score": 0.0}]),
            market_data_by_symbol={"510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}])},
            runtime_config=RuntimeConfig(
                timezone="Asia/Shanghai",
                intraday_enabled=True,
                intraday_interval_minutes=5,
                intraday_bar_frequency="5",
                intraday_lookback_bars=120,
                intraday_window_am_start="09:30",
                intraday_window_am_end="11:30",
                intraday_window_pm_start="13:00",
                intraday_window_pm_end="15:00",
                preclose_enabled=True,
                preclose_trigger_time="14:45",
                preclose_decision_time="14:50",
                preclose_output_dir="reports/preclose",
                hypothesis_weights={"trend_following": 1.8, "mean_reversion": 0.6, "momentum": 1.2},
                hypothesis_conflict_min_score=0.18,
                hypothesis_conflict_min_confidence=0.55,
                hypothesis_hold_min_score=0.28,
                hypothesis_hold_min_confidence=0.60,
                hypothesis_tiebreak_min_groups=2,
            ),
        )

        row = conclusion.iloc[0]
        self.assertEqual(row["long_term_action"], "BUY")
        self.assertEqual(row["short_term_action"], "SELL")
        self.assertEqual(row["hypothesis_consensus_action"], "BUY")
        self.assertTrue(bool(row["hypothesis_tiebreak_applied"]))
        self.assertEqual(row["overall_action"], "BUY")

    def test_resolve_overall_action_with_hypothesis_promotes_double_hold(self):
        runtime_config = RuntimeConfig(
            timezone="Asia/Shanghai",
            intraday_enabled=True,
            intraday_interval_minutes=5,
            intraday_bar_frequency="5",
            intraday_lookback_bars=120,
            intraday_window_am_start="09:30",
            intraday_window_am_end="11:30",
            intraday_window_pm_start="13:00",
            intraday_window_pm_end="15:00",
            preclose_enabled=True,
            preclose_trigger_time="14:45",
            preclose_decision_time="14:50",
            preclose_output_dir="reports/preclose",
            hypothesis_weights={"trend_following": 1.0},
            hypothesis_conflict_min_score=0.18,
            hypothesis_conflict_min_confidence=0.55,
            hypothesis_hold_min_score=0.28,
            hypothesis_hold_min_confidence=0.60,
            hypothesis_tiebreak_min_groups=2,
        )
        action, applied = _resolve_overall_action_with_hypothesis(
            long_term_action="HOLD",
            short_term_action="HOLD",
            data_status="OK",
            hypothesis_consensus={
                "hypothesis_consensus_action": "BUY",
                "hypothesis_consensus_score": 0.42,
                "hypothesis_consensus_confidence": 0.74,
                "hypothesis_active_group_count": 2,
                "hypothesis_consensus_supporting_evidence": "趋势跟随@long_term | 动量@short_term",
            },
            runtime_config=runtime_config,
        )

        self.assertTrue(applied)
        self.assertEqual(action, "BUY")

    def test_build_daily_conclusions_respects_runtime_tiebreak_thresholds(self):
        summary = self._summary().head(1)
        conservative_runtime = RuntimeConfig(
            timezone="Asia/Shanghai",
            intraday_enabled=True,
            intraday_interval_minutes=5,
            intraday_bar_frequency="5",
            intraday_lookback_bars=120,
            intraday_window_am_start="09:30",
            intraday_window_am_end="11:30",
            intraday_window_pm_start="13:00",
            intraday_window_pm_end="15:00",
            preclose_enabled=True,
            preclose_trigger_time="14:45",
            preclose_decision_time="14:50",
            preclose_output_dir="reports/preclose",
            hypothesis_weights={"trend_following": 1.0, "mean_reversion": 1.0, "momentum": 1.0},
            hypothesis_conflict_min_score=0.90,
            hypothesis_conflict_min_confidence=0.90,
            hypothesis_hold_min_score=0.90,
            hypothesis_hold_min_confidence=0.90,
            hypothesis_tiebreak_min_groups=3,
        )

        conclusion, _, _, _ = build_daily_conclusions(
            summary=summary,
            eod_d=pd.DataFrame(
                [
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "RSI_reversion_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Bollinger_reversion_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                ]
            ),
            eod_w=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "Triple_MA_strategy", "signal": "BUY"},
                ]
            ),
            eod_m=pd.DataFrame(),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame([{"symbol": "510300", "decision_signal": "HOLD", "decision_score": 0.0}]),
            market_data_by_symbol={"510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}])},
            runtime_config=conservative_runtime,
        )

        row = conclusion.iloc[0]
        self.assertEqual(row["hypothesis_consensus_action"], "BUY")
        self.assertFalse(bool(row["hypothesis_tiebreak_applied"]))
        self.assertEqual(row["overall_action"], "HOLD")

    def test_build_daily_conclusions_counts_unique_active_hypothesis_groups(self):
        summary = self._summary().head(1)
        conclusion, _, _, _ = build_daily_conclusions(
            summary=summary,
            eod_d=pd.DataFrame(
                [
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                ]
            ),
            eod_w=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                ]
            ),
            eod_m=pd.DataFrame(),
            intraday=pd.DataFrame(),
            preclose=pd.DataFrame([{"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.2}]),
            market_data_by_symbol={"510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}])},
        )

        row = conclusion.iloc[0]
        self.assertEqual(row["hypothesis_consensus_action"], "BUY")
        self.assertEqual(int(row["hypothesis_active_group_count"]), 2)

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

    def test_build_operation_view_mentions_hypothesis_tiebreak(self):
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
                    "short_term_action": "SELL",
                    "hypothesis_consensus_action": "BUY",
                    "hypothesis_tiebreak_applied": True,
                    "preclose_signal": "HOLD",
                    "overall_action": "BUY",
                    "data_status": "OK",
                }
            ]
        )

        operation_view = build_operation_view(conclusion)

        self.assertEqual(operation_view.iloc[0]["action_note"], "分组共识偏向 BUY，用于化解长短线冲突")
        self.assertIn("hypothesis_summary_text", operation_view.columns)

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
        self.assertIn("Hypothesis_Summary", sheet_names)
        self.assertIn("LongTerm_Evidence", sheet_names)
        self.assertIn("ShortTerm_Evidence", sheet_names)
        self.assertIn("Data_Gaps", sheet_names)
        self.assertEqual(sheet_names[0], "Operation_View")

    def test_build_daily_conclusion_frames_adds_hypothesis_summary(self):
        summary = self._summary().head(2)
        frames = build_daily_conclusion_frames(
            summary=summary,
            eod_d=pd.DataFrame(
                [
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                    {"date": "2026-03-10", "symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
                    {"date": "2026-03-10", "symbol": "000300", "strategy": "RSI_reversion_strategy", "signal": "BUY"},
                ]
            ),
            eod_w=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
                    {"date": "2026-03-07", "symbol": "000300", "strategy": "RSRS_strategy", "signal": "SELL"},
                ]
            ),
            eod_m=pd.DataFrame(
                [
                    {"date": "2026-03-07", "symbol": "510300", "strategy": "ETF_rotation_strategy", "signal": "BUY"},
                    {"date": "2026-03-07", "symbol": "000300", "strategy": "Momentum_60_strategy", "signal": "SELL"},
                ]
            ),
            intraday=pd.DataFrame(
                [
                    {"ts": "2026-03-10T14:45:00+08:00", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
                    {"ts": "2026-03-10T14:45:00+08:00", "symbol": "000300", "strategy": "MA_strategy", "signal": "SELL"},
                ]
            ),
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

        hypothesis_summary = frames["Hypothesis_Summary"]
        trend_buy = hypothesis_summary[
            (hypothesis_summary["symbol"] == "510300")
            & (hypothesis_summary["horizon"] == "short_term")
            & (hypothesis_summary["market_hypothesis"] == "trend_following")
        ].iloc[0]
        cross_asset = hypothesis_summary[
            (hypothesis_summary["symbol"] == "510300")
            & (hypothesis_summary["horizon"] == "long_term")
            & (hypothesis_summary["market_hypothesis"] == "cross_asset_allocation")
        ].iloc[0]

        self.assertEqual(trend_buy["market_hypothesis_label"], "趋势跟随")
        self.assertEqual(trend_buy["hypothesis_action"], "BUY")
        self.assertEqual(cross_asset["hypothesis_action"], "BUY")
        self.assertIn("ETF_rotation_strategy@EOD_M", cross_asset["hypothesis_supporting_evidence"])

    def test_load_daily_conclusion_context_keeps_intraday_target_date_when_ts_provided(self):
        @contextmanager
        def _fake_session_scope(_config=None):
            yield object()

        requested_ts = datetime(2026, 3, 10, 15, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        latest_signal_ts = datetime(2026, 3, 10, 14, 50, tzinfo=ZoneInfo("Asia/Shanghai"))
        summary = self._summary().head(1)

        with patch("signal_service.daily_conclusion_report.session_scope", _fake_session_scope), patch(
            "signal_service.daily_conclusion_report._resolve_eod_signal_dates",
            return_value={"D": date(2026, 3, 7), "W": date(2026, 3, 6), "M": date(2026, 3, 6)},
        ), patch(
            "signal_service.daily_conclusion_report.load_latest_intraday_signal_ts",
            return_value=latest_signal_ts,
        ), patch(
            "signal_service.daily_conclusion_report.load_signals_by_date",
            side_effect=[
                pd.DataFrame([{"date": "2026-03-07", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"}]),
                pd.DataFrame(),
                pd.DataFrame(),
            ],
        ), patch(
            "signal_service.daily_conclusion_report.load_intraday_signals",
            return_value=pd.DataFrame([{"ts": latest_signal_ts.isoformat(), "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"}]),
        ) as mock_load_intraday_signals, patch(
            "signal_service.daily_conclusion_report.load_market_prices_map",
            return_value={"510300": pd.DataFrame([{"date": "2026-03-07", "close": 4.56}])},
        ), patch(
            "signal_service.daily_conclusion_report.load_realtime_bars_map",
            return_value={"510300": pd.DataFrame([{"date": latest_signal_ts.isoformat(), "close": 4.60}])},
        ), patch(
            "signal_service.daily_conclusion_report.build_secondary_validation",
            return_value=pd.DataFrame(),
        ), patch(
            "signal_service.daily_conclusion_report.build_signal_summary",
            return_value=summary,
        ), patch(
            "signal_service.daily_conclusion_report.build_preclose_decisions",
            return_value=pd.DataFrame([{"symbol": "510300", "decision_signal": "BUY", "decision_score": 4.0}]),
        ) as mock_build_preclose:
            context = load_daily_conclusion_context(signal_date=requested_ts.date(), intraday_ts=requested_ts, symbols=["510300"])

        self.assertEqual(context["signal_date"], date(2026, 3, 10))
        self.assertEqual(context["intraday_ts"], latest_signal_ts)
        mock_load_intraday_signals.assert_called_once_with(ANY, latest_signal_ts, bar_frequency="5")
        mock_build_preclose.assert_called_once()
        self.assertEqual(mock_build_preclose.call_args.kwargs["analysis_mode"], "INTRADAY_PRE_CLOSE")
        self.assertEqual(mock_build_preclose.call_args.kwargs["signal_date"], date(2026, 3, 10))
        self.assertEqual(mock_build_preclose.call_args.kwargs["analysis_ts"], latest_signal_ts)

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
        hypothesis_counts = overview[overview["section"] == "hypothesis_consensus_count"].set_index("item")["value"].to_dict()
        preclose_counts = overview[overview["section"] == "preclose_signal_count"].set_index("item")["value"].to_dict()

        self.assertEqual(overall_counts["BUY"], "1")
        self.assertEqual(overall_counts["SELL"], "1")
        self.assertEqual(long_term_counts["BUY"], "1")
        self.assertEqual(long_term_counts["SELL"], "1")
        self.assertEqual(short_term_counts["BUY"], "1")
        self.assertEqual(short_term_counts["SELL"], "1")
        self.assertEqual(hypothesis_counts["BUY"], "1")
        self.assertEqual(hypothesis_counts["SELL"], "1")
        self.assertEqual(preclose_counts["BUY"], "1")
        self.assertEqual(preclose_counts["SELL"], "1")


if __name__ == "__main__":
    unittest.main()
