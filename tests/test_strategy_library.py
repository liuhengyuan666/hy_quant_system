from __future__ import annotations

import unittest

import pandas as pd

from strategy_engine.base import CrossSectionalStrategy, Signal, Strategy
from strategy_engine.library import list_strategy_names, list_strategy_names_by_horizon, list_strategy_names_by_mode, resolve_strategy_specs


def _make_frame(size: int, drift: float = 0.002) -> pd.DataFrame:
    closes = [100.0]
    for index in range(1, size):
        closes.append(closes[-1] * (1 + drift + ((index % 7) - 3) * 0.0008))

    dates = pd.date_range("2024-01-01", periods=size, freq="D")
    return pd.DataFrame(
        {
            "date": dates,
            "open": [value * 0.998 for value in closes],
            "high": [value * 1.01 for value in closes],
            "low": [value * 0.99 for value in closes],
            "close": closes,
            "volume": [10000 + (index * 25) for index in range(size)],
            "symbol": ["510300" for _ in range(size)],
        }
    )


class StrategyLibraryTests(unittest.TestCase):
    def test_strategy_count(self):
        names = list_strategy_names()
        self.assertEqual(len(names), 20)
        self.assertEqual(len(set(names)), 20)

    def test_resolve_subset(self):
        subset = ["MA_strategy", "ETF_rotation_strategy", "MultiFactor_strategy"]
        specs = resolve_strategy_specs(subset)
        self.assertEqual([item.name for item in specs], subset)

    def test_intraday_mode_filters_to_lightweight_subset(self):
        names = list_strategy_names_by_mode("intraday")
        self.assertIn("MA_strategy", names)
        self.assertIn("EMA_cross_strategy", names)
        self.assertNotIn("ETF_rotation_strategy", names)
        specs = resolve_strategy_specs(supported_mode="intraday")
        self.assertTrue(all("intraday" in item.supported_modes for item in specs))

    def test_strategy_horizons_are_partitioned(self):
        short_term = list_strategy_names_by_horizon("short_term")
        long_term = list_strategy_names_by_horizon("long_term")
        self.assertEqual(len(short_term), 12)
        self.assertEqual(len(long_term), 8)
        self.assertEqual(set(short_term).intersection(set(long_term)), set())
        self.assertIn("Momentum_60_strategy", long_term)
        self.assertIn("EMA_cross_strategy", short_term)

    def test_single_strategies_generate_signal(self):
        specs = resolve_strategy_specs()
        frame = _make_frame(320, drift=0.0018)
        allowed = {Signal.BUY, Signal.SELL, Signal.HOLD}

        for spec in specs:
            if spec.mode != "single" or not isinstance(spec.engine, Strategy):
                continue
            signal = spec.engine.generate_signal(frame)
            self.assertIn(signal, allowed, spec.name)

    def test_cross_strategies_generate_signals(self):
        specs = resolve_strategy_specs()
        frame_a = _make_frame(320, drift=0.0015)
        frame_b = _make_frame(320, drift=0.0006)
        frame_c = _make_frame(320, drift=0.0020)

        frame_a["symbol"] = "510300"
        frame_b["symbol"] = "159915"
        frame_c["symbol"] = "513130"

        data_by_symbol = {
            "510300": frame_a,
            "159915": frame_b,
            "513130": frame_c,
        }

        allowed = {Signal.BUY, Signal.SELL, Signal.HOLD}
        for spec in specs:
            if spec.mode != "cross" or not isinstance(spec.engine, CrossSectionalStrategy):
                continue
            if spec.universe == "etf":
                scoped = {key: value for key, value in data_by_symbol.items() if key in {"510300", "159915", "513130"}}
            else:
                scoped = data_by_symbol
            signals = spec.engine.generate_signals(scoped)
            self.assertTrue(set(signals.keys()).issubset(set(scoped.keys())))
            for value in signals.values():
                self.assertIn(value, allowed, spec.name)


if __name__ == "__main__":
    unittest.main()
