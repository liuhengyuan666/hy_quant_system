from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from config.settings import RuntimeConfig, load_runtime_config
from data_service.futu_realtime import _normalize_futu_kline, fetch_futu_intraday_bars, supports_futu_symbol
from data_service.realtime_index import fetch_intraday_index_bars


def _runtime_config() -> RuntimeConfig:
    content = """
[runtime]
timezone = "Asia/Shanghai"

[runtime.intraday]
enabled = true
interval_minutes = 5
bar_frequency = "5"
lookback_bars = 120
window_am_start = "09:30"
window_am_end = "11:30"
window_pm_start = "13:00"
window_pm_end = "15:00"

[runtime.preclose]
enabled = true
trigger_time = "14:45"
decision_time = "14:50"
output_dir = "reports/preclose"

[runtime.hk_realtime]
provider = "futu"

[runtime.hk_realtime.futu]
host = "127.0.0.1"
port = 11111
is_encrypt = false

[runtime.hk_realtime.futu.symbol_map]
HSTECH = "HK.TEST1"
HSCEI = "HK.TEST2"
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "runtime.toml"
        path.write_text(content, encoding="utf-8")
        return load_runtime_config(path)


class FutuRealtimeTests(unittest.TestCase):
    def test_supports_futu_symbol_only_when_configured(self) -> None:
        config = _runtime_config()
        self.assertTrue(supports_futu_symbol("HSTECH", runtime_config=config))
        self.assertFalse(supports_futu_symbol("HSAHP", runtime_config=config))

    def test_normalize_futu_kline(self) -> None:
        frame = pd.DataFrame(
            [
                {"time_key": "2026-03-09 10:40:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 1000},
                {"time_key": "2026-03-09 10:45:00", "open": 1.05, "high": 1.2, "low": 1.0, "close": 1.15, "volume": 1200},
            ]
        )
        normalized = _normalize_futu_kline(frame, symbol="HSTECH", bar_frequency="5")
        self.assertEqual(len(normalized.index), 2)
        self.assertEqual(normalized.iloc[-1]["source"], "futu")
        self.assertEqual(normalized.iloc[-1]["symbol"], "HSTECH")

    @patch("data_service.futu_realtime.OpenQuoteContext")
    @patch("data_service.futu_realtime._assert_futu_opend_reachable")
    def test_fetch_futu_intraday_bars(self, mock_reachable, mock_context) -> None:
        config = _runtime_config()
        frame = pd.DataFrame(
            [{"time_key": "2026-03-09 10:45:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 1000}]
        )
        ctx = MagicMock()
        ctx.subscribe.return_value = (0, None)
        ctx.get_cur_kline.return_value = (0, frame)
        mock_context.return_value = ctx

        actual = fetch_futu_intraday_bars("HSTECH", runtime_config=config)

        mock_reachable.assert_called_once_with("127.0.0.1", 11111)
        ctx.subscribe.assert_called_once()
        ctx.get_cur_kline.assert_called_once()
        ctx.close.assert_called_once()
        self.assertEqual(actual.iloc[-1]["source"], "futu")

    @patch("data_service.realtime_index.fetch_futu_intraday_bars")
    @patch("data_service.realtime_index.load_runtime_config")
    def test_fetch_intraday_index_bars_prefers_futu_for_configured_hk_symbol(self, mock_load_runtime_config, mock_fetch_futu_intraday_bars) -> None:
        config = _runtime_config()
        mock_load_runtime_config.return_value = config
        expected = pd.DataFrame(
            [{"ts": pd.Timestamp("2026-03-09 10:45:00"), "symbol": "HSTECH", "bar_frequency": "5", "source": "futu", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 1000.0}]
        )
        mock_fetch_futu_intraday_bars.return_value = expected

        actual = fetch_intraday_index_bars("HSTECH", period="5")

        mock_fetch_futu_intraday_bars.assert_called_once_with(symbol="HSTECH", period="5", runtime_config=config)
        self.assertTrue(actual.equals(expected))


if __name__ == "__main__":
    unittest.main()
