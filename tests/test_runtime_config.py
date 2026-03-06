from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

try:
    from config.settings import load_runtime_config
except Exception:
    load_runtime_config = None


@unittest.skipIf(load_runtime_config is None, "runtime dependencies unavailable")
class RuntimeConfigTests(unittest.TestCase):
    def test_defaults_when_file_missing(self):
        config = load_runtime_config(Path("__not_exists__.toml"))
        self.assertTrue(config.intraday_enabled)
        self.assertEqual(config.intraday_interval_minutes, 5)
        self.assertEqual(config.intraday_bar_frequency, "5")

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
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.toml"
            path.write_text(content, encoding="utf-8")
            config = load_runtime_config(path)
        self.assertEqual(config.intraday_interval_minutes, 7)
        self.assertEqual(config.intraday_bar_frequency, "10")
        self.assertEqual(config.intraday_window_pm_end, "14:55")
