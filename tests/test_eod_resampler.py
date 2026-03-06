from __future__ import annotations

import unittest

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from analysis.eod_resampler import normalize_bar_frequencies, resample_ohlcv
except Exception:
    normalize_bar_frequencies = None
    resample_ohlcv = None


@unittest.skipIf(pd is None or normalize_bar_frequencies is None or resample_ohlcv is None, "runtime dependencies unavailable")
class EodResamplerTests(unittest.TestCase):
    def test_normalize_bar_frequencies(self):
        self.assertEqual(normalize_bar_frequencies(["d", "W", "m", "d"]), ["D", "W", "M"])

    def test_weekly_resample_uses_last_trading_day(self):
        frame = pd.DataFrame(
            {
                "symbol": ["510300"] * 6,
                "date": pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]),
                "open": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                "high": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6],
                "low": [0.9, 1.8, 2.7, 3.6, 4.5, 5.4],
                "close": [1.05, 2.05, 3.05, 4.05, 5.05, 6.05],
                "volume": [10, 20, 30, 40, 50, 60],
            }
        )

        weekly = resample_ohlcv(frame, "W")
        self.assertEqual(len(weekly.index), 2)
        self.assertEqual(str(weekly.iloc[0]["date"]), "2026-03-06")
        self.assertAlmostEqual(float(weekly.iloc[0]["open"]), 1.0)
        self.assertAlmostEqual(float(weekly.iloc[0]["close"]), 5.05)
        self.assertAlmostEqual(float(weekly.iloc[0]["high"]), 5.5)
        self.assertAlmostEqual(float(weekly.iloc[0]["low"]), 0.9)
        self.assertAlmostEqual(float(weekly.iloc[0]["volume"]), 150.0)

    def test_monthly_resample_groups_by_calendar_month(self):
        frame = pd.DataFrame(
            {
                "symbol": ["000300"] * 4,
                "date": pd.to_datetime(["2026-02-26", "2026-02-27", "2026-03-02", "2026-03-03"]),
                "open": [10.0, 11.0, 12.0, 13.0],
                "high": [10.5, 11.5, 12.5, 13.5],
                "low": [9.5, 10.5, 11.5, 12.5],
                "close": [10.2, 11.2, 12.2, 13.2],
                "volume": [100, 200, 300, 400],
            }
        )

        monthly = resample_ohlcv(frame, "M")
        self.assertEqual(len(monthly.index), 2)
        self.assertEqual(str(monthly.iloc[0]["date"]), "2026-02-27")
        self.assertAlmostEqual(float(monthly.iloc[1]["volume"]), 700.0)


if __name__ == "__main__":
    unittest.main()
