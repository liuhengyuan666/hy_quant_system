from __future__ import annotations

from datetime import date
import unittest
from typing import Any, cast

import pandas as pd

from signal_service.secondary_validation import build_secondary_validation


def _market_frame(start_price: float, step: float, days: int = 120, volume: float = 1000.0) -> pd.DataFrame:
    closes = [start_price + (index * step) for index in range(days)]
    dates = pd.date_range("2025-10-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": [price * 0.997 for price in closes],
            "high": [price * 1.01 for price in closes],
            "low": [price * 0.99 for price in closes],
            "close": closes,
            "volume": [volume for _ in closes],
            "symbol": ["NA" for _ in closes],
        }
    )


class SecondaryValidationTests(unittest.TestCase):
    def test_build_secondary_validation_basic_shape(self):
        signals = pd.DataFrame(
            [
                {"date": "2026-03-07", "symbol": "000001", "name": "上证指数", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "000001", "name": "上证指数", "strategy": "RSRS_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "000001", "name": "上证指数", "strategy": "MACD_hist_strategy", "signal": "HOLD"},
                {"date": "2026-03-07", "symbol": "000852", "name": "中证1000", "strategy": "MA_strategy", "signal": "SELL"},
                {"date": "2026-03-07", "symbol": "000852", "name": "中证1000", "strategy": "RSRS_strategy", "signal": "SELL"},
                {"date": "2026-03-07", "symbol": "000852", "name": "中证1000", "strategy": "MACD_hist_strategy", "signal": "HOLD"},
            ]
        )

        market_data = {
            "000001": _market_frame(start_price=100.0, step=0.4),
            "000852": _market_frame(start_price=260.0, step=-0.5),
        }

        output = build_secondary_validation(
            signals_frame=signals,
            market_data_by_symbol=market_data,
            signal_date=date(2026, 3, 7),
        )
        payload = cast(dict[str, Any], output)
        rule_evaluations = cast(list[dict[str, Any]], payload["rule_evaluations"])
        symbol_reviews = cast(list[dict[str, Any]], payload["symbol_reviews"])

        self.assertEqual(payload["signal_date"], "2026-03-07")
        self.assertEqual(len(rule_evaluations), 7)
        self.assertEqual(len(symbol_reviews), 2)
        self.assertIn(payload["review_gate"], {"CONFIRM", "CAUTION", "REJECT"})

        by_symbol = {str(item["symbol"]): item for item in symbol_reviews}
        self.assertEqual(by_symbol["000001"]["primary_action"], "BUY")
        self.assertEqual(by_symbol["000852"]["primary_action"], "SELL")

    def test_build_secondary_validation_handles_missing_market_data(self):
        signals = pd.DataFrame(
            [
                {"date": "2026-03-07", "symbol": "399006", "name": "创业板指", "strategy": "MA_strategy", "signal": "BUY"},
                {"date": "2026-03-07", "symbol": "399006", "name": "创业板指", "strategy": "RSRS_strategy", "signal": "HOLD"},
            ]
        )

        output = build_secondary_validation(
            signals_frame=signals,
            market_data_by_symbol={},
            signal_date=date(2026, 3, 7),
        )
        payload = cast(dict[str, Any], output)
        symbol_reviews = cast(list[dict[str, Any]], payload["symbol_reviews"])

        self.assertEqual(len(symbol_reviews), 1)
        review = symbol_reviews[0]
        self.assertEqual(review["symbol"], "399006")
        self.assertIn("trend_up", review["market_metrics"])
        self.assertIn(payload["review_gate"], {"CONFIRM", "CAUTION", "REJECT", "INSUFFICIENT_DATA"})


if __name__ == "__main__":
    unittest.main()
