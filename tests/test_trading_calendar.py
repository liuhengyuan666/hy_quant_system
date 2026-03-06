from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

try:
    from config.settings import RuntimeConfig
    from core.trading_calendar import is_trading_session, latest_closed_trading_date
except Exception:
    latest_closed_trading_date = None
    is_trading_session = None
    RuntimeConfig = None


@unittest.skipIf(latest_closed_trading_date is None, "runtime dependencies unavailable")
class TradingCalendarTests(unittest.TestCase):
    def test_before_close_rolls_back_to_previous_weekday(self):
        reference = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(str(latest_closed_trading_date(reference)), "2026-03-06")

    def test_after_close_uses_same_day(self):
        reference = datetime(2026, 3, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(str(latest_closed_trading_date(reference)), "2026-03-10")

    def test_weekend_rolls_back_to_friday(self):
        reference = datetime(2026, 3, 8, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(str(latest_closed_trading_date(reference)), "2026-03-06")

    def test_trading_session_detects_lunch_break(self):
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
        )
        self.assertFalse(is_trading_session(datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")), runtime))
        self.assertTrue(is_trading_session(datetime(2026, 3, 10, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")), runtime))


if __name__ == "__main__":
    unittest.main()
