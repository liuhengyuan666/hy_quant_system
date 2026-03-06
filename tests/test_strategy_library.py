from __future__ import annotations

import unittest

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from strategy_engine.base import Signal
    from strategy_engine.library import list_strategy_names, list_strategy_names_by_mode, resolve_strategy_specs
except Exception:
    Signal = None
    list_strategy_names = None
    list_strategy_names_by_mode = None
    resolve_strategy_specs = None


def _make_frame(size: int, drift: float = 0.002) -> pd.DataFrame:
    if pd is None:
        raise RuntimeError("pandas unavailable")

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


@unittest.skipIf(
    pd is None or Signal is None or list_strategy_names is None or list_strategy_names_by_mode is None or resolve_strategy_specs is None,
    "runtime dependencies unavailable",
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

    def test_single_strategies_generate_signal(self):
        specs = resolve_strategy_specs()
        frame = _make_frame(320, drift=0.0018)
        allowed = {Signal.BUY, Signal.SELL, Signal.HOLD}

        for spec in specs:
            if spec.mode != "single":
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
            if spec.mode != "cross":
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
