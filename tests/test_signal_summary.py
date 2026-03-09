from __future__ import annotations

import unittest

import pandas as pd

from signal_service.summary_view import build_group_summary, build_push_candidates, build_signal_summary, build_top_candidates


class SignalSummaryTests(unittest.TestCase):
    def test_build_signal_summary_aligns_trend_and_intraday(self):
        eod_d = pd.DataFrame([
            {"date": "2026-03-09", "symbol": "510300", "strategy": "MA_strategy", "signal": "BUY"},
            {"date": "2026-03-09", "symbol": "159915", "strategy": "MA_strategy", "signal": "SELL"},
        ])
        eod_w = pd.DataFrame([
            {"date": "2026-03-09", "symbol": "510300", "strategy": "RSRS_strategy", "signal": "BUY"},
            {"date": "2026-03-09", "symbol": "159915", "strategy": "RSRS_strategy", "signal": "SELL"},
        ])
        eod_m = pd.DataFrame([
            {"date": "2026-03-09", "symbol": "510300", "strategy": "Momentum_20_strategy", "signal": "HOLD"},
            {"date": "2026-03-09", "symbol": "159915", "strategy": "Momentum_20_strategy", "signal": "SELL"},
        ])
        intraday = pd.DataFrame([
            {"ts": "2026-03-10T10:35:00+08:00", "symbol": "510300", "strategy": "EMA_cross_strategy", "signal": "BUY"},
            {"ts": "2026-03-10T10:35:00+08:00", "symbol": "159915", "strategy": "EMA_cross_strategy", "signal": "BUY"},
        ])
        secondary_validation = {
            "review_score": 85,
            "review_gate": "CONFIRM",
            "symbol_reviews": [
                {"symbol": "510300", "primary_action": "BUY", "secondary_action": "BUY_CONFIRM", "confidence": 90},
                {"symbol": "159915", "primary_action": "SELL", "secondary_action": "HOLD_OBSERVE", "confidence": 55},
            ],
        }

        summary = build_signal_summary(
            eod_d=eod_d,
            eod_w=eod_w,
            eod_m=eod_m,
            intraday=intraday,
            secondary_validation=secondary_validation,
        )

        first = summary[summary["symbol"] == "510300"].iloc[0]
        second = summary[summary["symbol"] == "159915"].iloc[0]
        self.assertEqual(first["eod_bias"], "BUY")
        self.assertEqual(first["alignment"], "ALIGNED")
        self.assertGreater(float(first["composite_score"]), 0.0)
        self.assertEqual(first["dashboard_action"], "PRIORITY_BUY")
        self.assertEqual(first["bucket"], "宽基ETF")
        self.assertEqual(first["secondary_action"], "BUY_CONFIRM")
        self.assertEqual(first["review_gate"], "CONFIRM")
        self.assertEqual(second["eod_bias"], "SELL")
        self.assertEqual(second["alignment"], "DIVERGED")
        self.assertEqual(second["dashboard_action"], "WATCHLIST")
        self.assertEqual(int(first["conviction_rank"]), 1)

    def test_build_signal_summary_ranks_by_composite_score(self):
        eod_d = pd.DataFrame(
            [
                {"date": "2026-03-09", "symbol": "A", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-09", "symbol": "B", "strategy": "MA_strategy", "signal": "SELL"},
            ]
        )
        eod_w = pd.DataFrame(
            [
                {"date": "2026-03-09", "symbol": "A", "strategy": "RSRS_strategy", "signal": "BUY"},
                {"date": "2026-03-09", "symbol": "B", "strategy": "RSRS_strategy", "signal": "HOLD"},
            ]
        )
        eod_m = pd.DataFrame(
            [
                {"date": "2026-03-09", "symbol": "A", "strategy": "Momentum_20_strategy", "signal": "BUY"},
                {"date": "2026-03-09", "symbol": "B", "strategy": "Momentum_20_strategy", "signal": "SELL"},
            ]
        )
        intraday = pd.DataFrame(
            [
                {"ts": "2026-03-10T10:35:00+08:00", "symbol": "A", "strategy": "EMA_cross_strategy", "signal": "BUY"},
                {"ts": "2026-03-10T10:35:00+08:00", "symbol": "B", "strategy": "EMA_cross_strategy", "signal": "SELL"},
            ]
        )
        secondary_validation = {
            "review_score": 78,
            "review_gate": "CONFIRM",
            "symbol_reviews": [
                {"symbol": "A", "primary_action": "BUY", "secondary_action": "BUY_CONFIRM", "confidence": 85},
                {"symbol": "B", "primary_action": "SELL", "secondary_action": "SELL_CONFIRM", "confidence": 60},
            ],
        }

        summary = build_signal_summary(
            eod_d=eod_d,
            eod_w=eod_w,
            eod_m=eod_m,
            intraday=intraday,
            secondary_validation=secondary_validation,
        )

        self.assertEqual(summary.iloc[0]["symbol"], "A")
        self.assertEqual(int(summary.iloc[0]["conviction_rank"]), 1)
        self.assertGreater(float(summary.iloc[0]["composite_score"]), abs(float(summary.iloc[1]["composite_score"])))

    def test_group_summary_and_top_candidates(self):
        summary = pd.DataFrame(
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
                    "secondary_confidence": 92.0,
                    "review_gate": "CONFIRM",
                    "composite_score": 6.5,
                    "dashboard_action": "PRIORITY_BUY",
                },
                {
                    "conviction_rank": 2,
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
                    "secondary_confidence": 88.0,
                    "review_gate": "CONFIRM",
                    "composite_score": -7.5,
                    "dashboard_action": "PRIORITY_SELL",
                },
            ]
        )

        groups = build_group_summary(summary)
        top = build_top_candidates(summary, limit=2)

        self.assertEqual(set(groups["bucket"].tolist()), {"宽基ETF", "行业"})
        self.assertEqual(groups.iloc[0]["top_symbol"], "510300")
        self.assertIn("avg_secondary_confidence", groups.columns)
        self.assertEqual(top.iloc[0]["direction"], "BUY")
        self.assertEqual(top.iloc[1]["direction"], "SELL")
        self.assertEqual(top.iloc[0]["secondary_action"], "BUY_CONFIRM")

    def test_build_push_candidates_limits_to_top_three(self):
        current = pd.DataFrame(
            [
                {"conviction_rank": 1, "symbol": "A", "display_symbol": "EA", "name": "AETF", "bucket": "宽基ETF", "dashboard_action": "PRIORITY_BUY", "composite_score": 8.0, "secondary_action": "BUY_CONFIRM", "secondary_confidence": 90.0, "review_gate": "CONFIRM"},
                {"conviction_rank": 2, "symbol": "B", "display_symbol": "EB", "name": "BETF", "bucket": "宽基ETF", "dashboard_action": "PRIORITY_SELL", "composite_score": -7.0, "secondary_action": "SELL_CONFIRM", "secondary_confidence": 88.0, "review_gate": "CONFIRM"},
                {"conviction_rank": 3, "symbol": "C", "display_symbol": "EC", "name": "CETF", "bucket": "行业", "dashboard_action": "WATCHLIST", "composite_score": 3.0, "secondary_action": "HOLD_OBSERVE", "secondary_confidence": 60.0, "review_gate": "CAUTION"},
                {"conviction_rank": 4, "symbol": "D", "display_symbol": "ED", "name": "DETF", "bucket": "行业", "dashboard_action": "TREND_BUY", "composite_score": 2.0, "secondary_action": "BUY_CONFIRM", "secondary_confidence": 72.0, "review_gate": "CONFIRM"},
            ]
        )
        previous = pd.DataFrame(
            [
                {"symbol": "A", "dashboard_action": "TREND_BUY", "composite_score": 5.0, "conviction_rank": 3, "review_gate": "CAUTION", "secondary_action": "HOLD_OBSERVE"},
                {"symbol": "B", "dashboard_action": "TREND_SELL", "composite_score": -4.0, "conviction_rank": 4, "review_gate": "CAUTION", "secondary_action": "HOLD_OBSERVE"},
                {"symbol": "C", "dashboard_action": "NEUTRAL", "composite_score": 0.5, "conviction_rank": 8, "review_gate": "CONFIRM", "secondary_action": "HOLD_OBSERVE"},
                {"symbol": "D", "dashboard_action": "TREND_BUY", "composite_score": 1.8, "conviction_rank": 5, "review_gate": "CONFIRM", "secondary_action": "BUY_CONFIRM"},
            ]
        )

        pushed = build_push_candidates(current, previous_summary=previous, limit=3)

        self.assertEqual(len(pushed.index), 3)
        self.assertEqual(int(pushed.iloc[0]["push_rank"]), 1)
        self.assertEqual(pushed.iloc[0]["symbol"], "A")
        self.assertTrue(all(symbol in {"A", "B", "C", "D"} for symbol in pushed["symbol"].tolist()))

    def test_build_push_candidates_coerces_previous_symbol_types(self):
        current = pd.DataFrame(
            [
                {"conviction_rank": 1, "symbol": "510300", "display_symbol": "E510300", "name": "沪深300ETF", "bucket": "宽基ETF", "dashboard_action": "PRIORITY_BUY", "composite_score": 8.0, "secondary_action": "BUY_CONFIRM", "secondary_confidence": 90.0, "review_gate": "CONFIRM"}
            ]
        )
        previous = pd.DataFrame(
            [
                {"symbol": 510300, "dashboard_action": "TREND_BUY", "composite_score": 5.0, "conviction_rank": 3, "review_gate": "CAUTION", "secondary_action": "HOLD_OBSERVE"}
            ]
        )

        pushed = build_push_candidates(current, previous_summary=previous, limit=3)

        self.assertEqual(len(pushed.index), 1)
        self.assertEqual(pushed.iloc[0]["symbol"], "510300")
        self.assertEqual(pushed.iloc[0]["previous_dashboard_action"], "TREND_BUY")
