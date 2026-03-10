from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from config.settings import load_runtime_config


class RuntimeConfigTests(unittest.TestCase):
    def test_defaults_when_file_missing(self):
        config = load_runtime_config(Path("__not_exists__.toml"))
        self.assertTrue(config.intraday_enabled)
        self.assertEqual(config.intraday_interval_minutes, 5)
        self.assertEqual(config.intraday_bar_frequency, "5")
        self.assertTrue(config.preclose_enabled)
        self.assertEqual(config.preclose_trigger_time, "14:45")
        self.assertEqual(config.hk_realtime_provider, "none")
        self.assertEqual(config.hk_realtime_futu_host, "127.0.0.1")
        self.assertEqual(config.hk_realtime_futu_port, 11111)
        self.assertEqual(config.hk_realtime_futu_symbol_map, {})
        self.assertEqual(config.hypothesis_weights, {})
        self.assertEqual(config.hypothesis_conflict_min_score, 0.18)
        self.assertEqual(config.hypothesis_conflict_min_confidence, 0.55)
        self.assertEqual(config.hypothesis_hold_min_score, 0.28)
        self.assertEqual(config.hypothesis_hold_min_confidence, 0.60)
        self.assertEqual(config.hypothesis_tiebreak_min_groups, 2)

    def test_reads_custom_values(self):
        content = """
[runtime]
timezone = "Asia/Shanghai"

[runtime.intraday]
enabled = true
interval_minutes = 7
bar_frequency = "10"
lookback_bars = 88
window_am_start = "09:35"
window_am_end = "11:25"
window_pm_start = "13:05"
window_pm_end = "14:55"

[runtime.preclose]
enabled = false
trigger_time = "14:40"
decision_time = "14:50"
output_dir = "reports/custom-preclose"

[runtime.hypothesis.weights]
trend_following = 1.4
mean_reversion = 0.8
cross_asset_allocation = 1.3

[runtime.hypothesis.tiebreak]
conflict_min_score = 0.22
conflict_min_confidence = 0.61
hold_min_score = 0.35
hold_min_confidence = 0.72
min_groups = 3

[runtime.hk_realtime]
provider = "futu"

[runtime.hk_realtime.futu]
host = "127.0.0.1"
port = 21111
is_encrypt = true

[runtime.hk_realtime.futu.symbol_map]
HSTECH = "HK.CUSTOM1"
HSCEI = "HK.CUSTOM2"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.toml"
            path.write_text(content, encoding="utf-8")
            config = load_runtime_config(path)
        self.assertEqual(config.intraday_interval_minutes, 7)
        self.assertEqual(config.intraday_bar_frequency, "10")
        self.assertEqual(config.intraday_window_pm_end, "14:55")
        self.assertFalse(config.preclose_enabled)
        self.assertEqual(config.preclose_trigger_time, "14:40")
        self.assertEqual(config.preclose_output_dir, "reports/custom-preclose")
        self.assertEqual(config.hk_realtime_provider, "futu")
        self.assertEqual(config.hk_realtime_futu_port, 21111)
        self.assertTrue(config.hk_realtime_futu_is_encrypt)
        self.assertEqual(config.hk_realtime_futu_symbol_map, {"HSTECH": "HK.CUSTOM1", "HSCEI": "HK.CUSTOM2"})
        self.assertEqual(config.hypothesis_weights, {"trend_following": 1.4, "mean_reversion": 0.8, "cross_asset_allocation": 1.3})
        self.assertEqual(config.hypothesis_conflict_min_score, 0.22)
        self.assertEqual(config.hypothesis_conflict_min_confidence, 0.61)
        self.assertEqual(config.hypothesis_hold_min_score, 0.35)
        self.assertEqual(config.hypothesis_hold_min_confidence, 0.72)
        self.assertEqual(config.hypothesis_tiebreak_min_groups, 3)
