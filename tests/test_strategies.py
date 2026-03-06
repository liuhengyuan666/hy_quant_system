from __future__ import annotations

import unittest

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from strategy_engine.base import Signal
    from strategy_engine.etf_rotation import ETFRotationStrategy
    from strategy_engine.ma_trend import MATrendStrategy
    from strategy_engine.multifactor import MultiFactorStrategy
    from strategy_engine.rsrs_timing import RSRSTimingStrategy
except Exception:
    Signal = None
    ETFRotationStrategy = None
    MATrendStrategy = None
    MultiFactorStrategy = None
    RSRSTimingStrategy = None


def _make_frame(closes: list[float]):
    if pd is None:
        raise RuntimeError("pandas unavailable")
    size = len(closes)
    dates = pd.date_range("2024-01-01", periods=size, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [value * 1.01 for value in closes],
            "low": [value * 0.99 for value in closes],
            "close": closes,
            "volume": [1_000 + idx * 10 for idx in range(size)],
        }
    )


@unittest.skipIf(
    pd is None
    or Signal is None
    or ETFRotationStrategy is None
    or MATrendStrategy is None
    or MultiFactorStrategy is None
    or RSRSTimingStrategy is None,
    "runtime dependencies unavailable",
)
class StrategyTests(unittest.TestCase):
    def test_ma_strategy_buy(self):
        data = _make_frame([float(value) for value in range(1, 121)])
        strategy = MATrendStrategy()
        signal = strategy.generate_signal(data)
        self.assertEqual(signal, Signal.BUY)

    def test_ma_strategy_sell(self):
        data = _make_frame([float(value) for value in range(121, 1, -1)])
        strategy = MATrendStrategy()
        signal = strategy.generate_signal(data)
        self.assertEqual(signal, Signal.SELL)

    def test_rsrs_strategy_runs(self):
        data = _make_frame([float(value) for value in range(1, 160)])
        strategy = RSRSTimingStrategy(regression_window=18, zscore_window=60)
        signal = strategy.generate_signal(data)
        self.assertIn(signal, {Signal.BUY, Signal.SELL, Signal.HOLD})

    def test_etf_rotation_selects_winner(self):
        strategy = ETFRotationStrategy(lookback_days=20)
        signals = strategy.generate_signals(
            {
                "510300": _make_frame([1.0 + value * 0.01 for value in range(60)]),
                "159915": _make_frame([1.0 + value * 0.008 for value in range(60)]),
            }
        )
        self.assertEqual(signals["510300"], Signal.BUY)
        self.assertEqual(signals["159915"], Signal.SELL)

    def test_multifactor_selects_symbol(self):
        strategy = MultiFactorStrategy(lookback_days=20)
        signals = strategy.generate_signals(
            {
                "513130": _make_frame([1.0 + value * 0.015 for value in range(80)]),
                "159915": _make_frame([1.0 + value * 0.003 for value in range(80)]),
            }
        )
        self.assertEqual(signals["513130"], Signal.BUY)


if __name__ == "__main__":
    unittest.main()
