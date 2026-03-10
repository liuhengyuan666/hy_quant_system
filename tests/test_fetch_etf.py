from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

import pandas as pd

from data_service.fetch_etf import fetch_etf_history


class FetchEtfTests(unittest.TestCase):
    @patch("data_service.fetch_etf.normalize_ohlcv")
    @patch("data_service.fetch_etf.ak")
    def test_fetch_etf_history_uses_proxy_disabled_context(self, mock_ak, mock_normalize_ohlcv):
        raw = pd.DataFrame([{"日期": "2026-03-10", "收盘": 4.683}])
        mock_ak.fund_etf_hist_em.return_value = raw
        mock_normalize_ohlcv.return_value = pd.DataFrame([{"date": "2026-03-10", "close": 4.683, "symbol": "510300"}])

        entered = {"value": False}

        @contextmanager
        def fake_disable_requests_env_proxy():
            entered["value"] = True
            yield

        with patch("data_service.fetch_etf.disable_requests_env_proxy", fake_disable_requests_env_proxy):
            result = fetch_etf_history(symbol="510300", start_date="20260301", end_date="20260310")

        self.assertTrue(entered["value"])
        mock_ak.fund_etf_hist_em.assert_called_once_with(
            symbol="510300",
            period="daily",
            start_date="20260301",
            end_date="20260310",
            adjust="qfq",
        )
        self.assertEqual(result.iloc[0]["symbol"], "510300")


if __name__ == "__main__":
    unittest.main()
