from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from data_service.realtime_etf import fetch_intraday_etf_bars
from data_service.realtime_index import fetch_intraday_index_bars
from data_service.tdx_realtime import (
    _normalize_tdx_bars,
    resolve_tdx_index_market,
    resolve_tdx_security_market,
    supports_tdx_symbol,
)


class TdxRealtimeTests(unittest.TestCase):
    def test_supports_tdx_symbol_only_for_numeric_codes(self) -> None:
        self.assertTrue(supports_tdx_symbol("510300"))
        self.assertFalse(supports_tdx_symbol("HSTECH"))

    def test_resolve_tdx_markets(self) -> None:
        self.assertEqual(resolve_tdx_index_market("000300"), 1)
        self.assertEqual(resolve_tdx_index_market("399006"), 0)
        self.assertEqual(resolve_tdx_security_market("510300"), 1)
        self.assertEqual(resolve_tdx_security_market("159915"), 0)

    def test_normalize_tdx_bars(self) -> None:
        frame = _normalize_tdx_bars(
            rows=[
                {"open": 4.58, "high": 4.59, "low": 4.57, "close": 4.585, "vol": 12345, "datetime": "2026-03-09 10:35:00"},
                {"open": 4.585, "high": 4.586, "low": 4.579, "close": 4.581, "vol": 45678, "datetime": "2026-03-09 10:40:00"},
            ],
            symbol="510300",
            bar_frequency="5",
        )
        self.assertEqual(list(frame.columns), ["ts", "symbol", "bar_frequency", "source", "open", "high", "low", "close", "volume"])
        self.assertEqual(len(frame.index), 2)
        self.assertEqual(frame.iloc[-1]["symbol"], "510300")
        self.assertEqual(frame.iloc[-1]["source"], "pytdx")
        self.assertEqual(float(frame.iloc[-1]["volume"]), 45678.0)

    @patch("data_service.realtime_index.fetch_tdx_index_bars")
    def test_fetch_intraday_index_bars_prefers_tdx_for_numeric_symbol(self, mock_fetch_tdx_index_bars) -> None:
        expected = pd.DataFrame(
            [{"ts": pd.Timestamp("2026-03-09 10:40:00"), "symbol": "000300", "bar_frequency": "5", "source": "pytdx", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
        )
        mock_fetch_tdx_index_bars.return_value = expected

        actual = fetch_intraday_index_bars("000300", period="5")

        mock_fetch_tdx_index_bars.assert_called_once_with(symbol="000300", period="5")
        self.assertTrue(actual.equals(expected))

    @patch("data_service.realtime_etf.fetch_tdx_security_bars")
    def test_fetch_intraday_etf_bars_prefers_tdx_for_numeric_symbol(self, mock_fetch_tdx_security_bars) -> None:
        expected = pd.DataFrame(
            [{"ts": pd.Timestamp("2026-03-09 10:40:00"), "symbol": "510300", "bar_frequency": "5", "source": "pytdx", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
        )
        mock_fetch_tdx_security_bars.return_value = expected

        actual = fetch_intraday_etf_bars("510300", period="5")

        mock_fetch_tdx_security_bars.assert_called_once_with(symbol="510300", period="5")
        self.assertTrue(actual.equals(expected))


if __name__ == "__main__":
    unittest.main()
