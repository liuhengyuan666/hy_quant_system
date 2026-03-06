from __future__ import annotations

import unittest

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from config.settings import SymbolMeta
    from signal_service.symbol_meta import enrich_signal_frame_with_symbol_names
except Exception:
    SymbolMeta = None
    enrich_signal_frame_with_symbol_names = None


@unittest.skipIf(
    pd is None or SymbolMeta is None or enrich_signal_frame_with_symbol_names is None,
    "runtime dependencies unavailable",
)
class SymbolMetaTests(unittest.TestCase):
    def test_enrich_signal_frame_with_names(self):
        frame = pd.DataFrame(
            [
                {
                    "date": "2026-03-07",
                    "symbol": "000001",
                    "strategy": "MA_strategy",
                    "signal": "BUY",
                    "score": None,
                    "meta": None,
                },
                {
                    "date": "2026-03-07",
                    "symbol": "999999",
                    "strategy": "MA_strategy",
                    "signal": "SELL",
                    "score": None,
                    "meta": None,
                },
            ]
        )

        mapping = {
            "000001": SymbolMeta(name="上证指数", display_symbol="1A0001"),
        }

        result = enrich_signal_frame_with_symbol_names(frame, symbol_meta_map=mapping)

        self.assertIn("name", result.columns)
        self.assertIn("display_symbol", result.columns)
        self.assertEqual(result.loc[0, "name"], "上证指数")
        self.assertEqual(result.loc[0, "display_symbol"], "1A0001")
        self.assertEqual(result.loc[1, "name"], "999999")
        self.assertEqual(result.loc[1, "display_symbol"], "999999")

    def test_enrich_preserves_output_column_order(self):
        frame = pd.DataFrame(
            [
                {
                    "date": "2026-03-07",
                    "symbol": "000905",
                    "strategy": "RSRS_strategy",
                    "signal": "HOLD",
                    "score": None,
                    "meta": None,
                }
            ]
        )
        result = enrich_signal_frame_with_symbol_names(
            frame,
            symbol_meta_map={"000905": SymbolMeta(name="中证500", display_symbol="1A0905")},
        )
        self.assertEqual(
            result.columns.tolist()[:8],
            ["date", "symbol", "display_symbol", "name", "strategy", "signal", "score", "meta"],
        )


if __name__ == "__main__":
    unittest.main()
