from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from signal_service.preclose_decision import build_preclose_decisions, run_preclose_analysis


class PrecloseDecisionTests(unittest.TestCase):
    def test_build_preclose_decisions_favors_buy_on_healthy_pullback(self):
        summary = pd.DataFrame(
            [
                {
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "eod_d": "BUY",
                    "eod_w": "BUY",
                    "eod_m": "BUY",
                    "intraday": "BUY",
                    "eod_bias": "BUY",
                    "alignment": "ALIGNED",
                    "secondary_action": "BUY_CONFIRM",
                    "secondary_confidence": 92.0,
                    "review_gate": "CONFIRM",
                    "review_score": 88.0,
                    "composite_score": 4.2,
                    "dashboard_action": "PRIORITY_BUY",
                    "conviction_rank": 1,
                }
            ]
        )
        market_data_by_symbol = {
            "510300": pd.DataFrame(
                [
                    {"date": "2026-01-01", "open": 3.80, "high": 3.82, "low": 3.78, "close": 3.81, "volume": 1000},
                    *[
                        {"date": f"2026-02-{day:02d}", "open": 4.00 + day * 0.01, "high": 4.02 + day * 0.01, "low": 3.98 + day * 0.01, "close": 4.00 + day * 0.01, "volume": 1000 + day}
                        for day in range(1, 25)
                    ],
                    *[
                        {"date": f"2026-03-{day:02d}", "open": 4.30 + day * 0.01, "high": 4.34 + day * 0.01, "low": 4.28 + day * 0.01, "close": 4.31 + day * 0.01, "volume": 1100 + day}
                        for day in range(1, 10)
                    ],
                ]
            )
        }
        intraday_bars = {
            "510300": pd.DataFrame(
                [
                    {"date": datetime(2026, 3, 10, 14, 35), "open": 4.58, "high": 4.60, "low": 4.56, "close": 4.59},
                    {"date": datetime(2026, 3, 10, 14, 40), "open": 4.59, "high": 4.61, "low": 4.57, "close": 4.58},
                    {"date": datetime(2026, 3, 10, 14, 45), "open": 4.58, "high": 4.59, "low": 4.55, "close": 4.56},
                ]
            )
        }

        result = build_preclose_decisions(
            summary=summary,
            market_data_by_symbol=market_data_by_symbol,
            intraday_bars_by_symbol=intraday_bars,
            analysis_mode="INTRADAY_PRE_CLOSE",
            signal_date=date(2026, 3, 10),
            analysis_ts=datetime(2026, 3, 10, 14, 45),
        )

        self.assertEqual(result.iloc[0]["decision_signal"], "BUY")
        self.assertIn("healthy_pullback", result.iloc[0]["decision_reason"])
        self.assertEqual(result.iloc[0]["trend_state"], "UPTREND")

    def test_build_preclose_decisions_blocks_sell_when_oversold(self):
        summary = pd.DataFrame(
            [
                {
                    "symbol": "512800",
                    "display_symbol": "E512800",
                    "name": "银行ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                    "eod_d": "SELL",
                    "eod_w": "SELL",
                    "eod_m": "SELL",
                    "intraday": "SELL",
                    "eod_bias": "SELL",
                    "alignment": "ALIGNED",
                    "secondary_action": "SELL_CONFIRM",
                    "secondary_confidence": 86.0,
                    "review_gate": "CONFIRM",
                    "review_score": 82.0,
                    "composite_score": -3.8,
                    "dashboard_action": "PRIORITY_SELL",
                    "conviction_rank": 1,
                }
            ]
        )
        market_data_by_symbol = {
            "512800": pd.DataFrame(
                [
                    *[
                        {"date": f"2026-01-{day:02d}", "open": 1.20, "high": 1.21, "low": 1.18, "close": 1.20 - day * 0.002, "volume": 1200 + day}
                        for day in range(1, 28)
                    ],
                    *[
                        {"date": f"2026-02-{day:02d}", "open": 1.10, "high": 1.11, "low": 1.06, "close": 1.10 - day * 0.002, "volume": 1300 + day}
                        for day in range(1, 28)
                    ],
                    {"date": "2026-03-09", "open": 0.95, "high": 0.96, "low": 0.90, "close": 0.91, "volume": 1800},
                    {"date": "2026-03-10", "open": 0.91, "high": 0.92, "low": 0.86, "close": 0.87, "volume": 2000},
                ]
            )
        }

        result = build_preclose_decisions(
            summary=summary,
            market_data_by_symbol=market_data_by_symbol,
            intraday_bars_by_symbol=None,
            analysis_mode="POST_CLOSE",
            signal_date=date(2026, 3, 10),
            analysis_ts=None,
        )

        self.assertEqual(result.iloc[0]["decision_signal"], "HOLD")
        self.assertIn("oversold_sell_penalty", result.iloc[0]["decision_reason"])

    def test_build_preclose_decisions_includes_fallback_symbol_as_hold_when_no_data(self):
        summary = pd.DataFrame(
            [
                {
                    "symbol": "510300",
                    "display_symbol": "E510300",
                    "name": "沪深300ETF",
                    "asset_type": "ETF",
                    "bucket": "宽基ETF",
                    "eod_d": "BUY",
                    "eod_w": "BUY",
                    "eod_m": "BUY",
                    "intraday": "HOLD",
                    "eod_bias": "BUY",
                    "alignment": "NEUTRAL",
                    "secondary_action": "BUY_CONFIRM",
                    "secondary_confidence": 85.0,
                    "review_gate": "CONFIRM",
                    "review_score": 80.0,
                    "composite_score": 4.0,
                    "dashboard_action": "TREND_BUY",
                    "conviction_rank": 1,
                }
            ]
        )

        result = build_preclose_decisions(
            summary=summary,
            market_data_by_symbol={"510300": pd.DataFrame([{"date": "2026-03-10", "close": 4.56}]), "HSAHP": pd.DataFrame()},
            intraday_bars_by_symbol=None,
            analysis_mode="POST_CLOSE",
            signal_date=date(2026, 3, 10),
            analysis_ts=None,
            fallback_symbols=["510300", "HSAHP"],
        )

        fallback_row = result[result["symbol"] == "HSAHP"].iloc[0]
        self.assertEqual(fallback_row["decision_signal"], "HOLD")
        self.assertIn("no_market_data", fallback_row["decision_reason"])

    def test_build_preclose_decisions_neutralizes_existing_summary_when_market_data_missing(self):
        summary = pd.DataFrame(
            [
                {
                    "symbol": "515880",
                    "display_symbol": "E515880",
                    "name": "通信ETF",
                    "asset_type": "ETF",
                    "bucket": "行业",
                    "eod_d": "MIXED",
                    "eod_w": "MIXED",
                    "eod_m": "MIXED",
                    "intraday": "HOLD",
                    "eod_bias": "HOLD",
                    "alignment": "NEUTRAL",
                    "secondary_action": "BUY_CONFIRM",
                    "secondary_confidence": 75.0,
                    "review_gate": "CONFIRM",
                    "review_score": 95.0,
                    "composite_score": 1.0,
                    "dashboard_action": "NEUTRAL",
                    "conviction_rank": 1,
                }
            ]
        )

        result = build_preclose_decisions(
            summary=summary,
            market_data_by_symbol={"515880": pd.DataFrame()},
            intraday_bars_by_symbol=None,
            analysis_mode="POST_CLOSE",
            signal_date=date(2026, 3, 10),
            analysis_ts=None,
        )

        row = result.iloc[0]
        self.assertEqual(row["decision_signal"], "HOLD")
        self.assertEqual(float(row["decision_score"]), 0.0)
        self.assertEqual(row["eod_d"], "NO_DATA")
        self.assertEqual(row["review_gate"], "INSUFFICIENT_DATA")
        self.assertEqual(row["decision_reason"], "no_market_data")

    @patch("signal_service.preclose_decision.export_preclose_decisions")
    @patch("signal_service.preclose_decision.build_preclose_decisions")
    @patch("signal_service.preclose_decision.build_signal_summary")
    @patch("signal_service.preclose_decision.build_secondary_validation")
    @patch("signal_service.preclose_decision.load_realtime_bars_map")
    @patch("signal_service.preclose_decision.load_intraday_signals")
    @patch("signal_service.preclose_decision.load_market_prices_map")
    @patch("signal_service.preclose_decision.load_signals_by_date")
    @patch("signal_service.preclose_decision.load_latest_signal_date_on_or_before")
    @patch("signal_service.preclose_decision.resolve_preclose_signal_date")
    @patch("signal_service.preclose_decision.load_runtime_config")
    @patch("signal_service.preclose_decision.load_universe_config")
    @patch("signal_service.preclose_decision.session_scope")
    def test_run_preclose_analysis_resolves_daily_signal_date_on_or_before_for_intraday_snapshot(
        self,
        mock_session_scope,
        mock_load_universe,
        mock_load_runtime,
        mock_resolve_signal_date,
        mock_latest_signal_date,
        mock_load_signals_by_date,
        mock_load_market_prices_map,
        mock_load_intraday_signals,
        mock_load_realtime_bars_map,
        mock_build_secondary_validation,
        mock_build_signal_summary,
        mock_build_preclose_decisions,
        mock_export_preclose_decisions,
    ):
        session = MagicMock()
        session_context = MagicMock()
        session_context.__enter__.return_value = session
        session_context.__exit__.return_value = False
        mock_session_scope.return_value = session_context
        mock_load_universe.return_value = SimpleNamespace(index_symbols=["000300"], etf_symbols=["510300"])
        mock_load_runtime.return_value = SimpleNamespace(intraday_bar_frequency="5", preclose_output_dir="reports/preclose")
        mock_resolve_signal_date.return_value = date(2026, 3, 10)
        mock_latest_signal_date.side_effect = [date(2026, 3, 7), date(2026, 3, 7), date(2026, 3, 7)]
        mock_load_signals_by_date.side_effect = [pd.DataFrame([{"symbol": "000300", "signal": "BUY"}]), pd.DataFrame(), pd.DataFrame()]
        mock_load_market_prices_map.return_value = {"000300": pd.DataFrame([{"date": "2026-03-07", "close": 3800.0}]), "510300": pd.DataFrame([{"date": "2026-03-07", "close": 4.56}])}
        mock_load_intraday_signals.return_value = pd.DataFrame([{"symbol": "000300", "signal": "BUY"}])
        mock_load_realtime_bars_map.return_value = {"000300": pd.DataFrame(), "510300": pd.DataFrame()}
        mock_build_secondary_validation.return_value = {}
        mock_build_signal_summary.return_value = pd.DataFrame([{"symbol": "000300", "conviction_rank": 1}])
        mock_build_preclose_decisions.return_value = pd.DataFrame([{"symbol": "000300", "decision_signal": "HOLD"}])
        mock_export_preclose_decisions.return_value = {"csv_path": Path("reports/preclose/preclose.csv"), "json_path": Path("reports/preclose/preclose.json")}

        result = run_preclose_analysis(signal_ts=datetime(2026, 3, 10, 14, 45), use_intraday_snapshot=True)

        self.assertEqual(result["signal_date"], "2026-03-10")
        first_latest_call = mock_latest_signal_date.call_args_list[0]
        self.assertEqual(first_latest_call.kwargs["bar_frequency"], "D")
        self.assertEqual(first_latest_call.args[1], date(2026, 3, 10))
        first_load_signals = mock_load_signals_by_date.call_args_list[0]
        self.assertEqual(first_load_signals.args[1], date(2026, 3, 7))
        self.assertEqual(mock_build_preclose_decisions.call_args.kwargs["fallback_symbols"], ["000300", "510300"])


if __name__ == "__main__":
    unittest.main()
