from __future__ import annotations

from datetime import date, datetime
import unittest

from zoneinfo import ZoneInfo

from config.settings import RuntimeConfig
from scheduler.intraday_runner import _should_trigger_preclose


class IntradayRunnerTests(unittest.TestCase):
    def test_should_trigger_preclose_only_once_per_day(self):
        runtime = RuntimeConfig(
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
        )
        current = datetime(2026, 3, 10, 14, 46, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertTrue(_should_trigger_preclose(current, runtime=runtime, last_triggered_date=None))
        self.assertFalse(_should_trigger_preclose(current, runtime=runtime, last_triggered_date=date(2026, 3, 10)))


if __name__ == "__main__":
    unittest.main()
